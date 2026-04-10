"""
=============================================================================
STRESS DETECTION - FULL ML TRAINING PIPELINE
=============================================================================
Sensors  : MAX30102 (Heart Rate, SpO2) + AD8232 (ECG/HRV)
Dataset  : SWELL-HRV (Kaggle) + WESAD (UCI) — see README comments below
Hardware : ESP32 → Flask → React
Output   : model.pkl + scaler.pkl + feature_names.pkl (load in Flask)

DATASETS:
  1. SWELL-HRV (easiest, CSV, ready immediately):
     https://www.kaggle.com/datasets/qiriro/swell-heart-rate-variability-hrv
     → Download and set SWELL_CSV_PATH below

  2. WESAD (more accurate, requires preprocessing):
     https://archive.ics.uci.edu/dataset/465/wesad
     → Run wesad_preprocess() after downloading

Install dependencies:
  pip install pandas numpy scikit-learn matplotlib seaborn heartpy scipy joblib imbalanced-learn
=============================================================================
"""

import os
import pickle
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from scipy import signal, stats
from scipy.fft import fft, fftfreq

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import (
    train_test_split, StratifiedKFold, cross_val_score, GridSearchCV
)
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score,
    roc_auc_score, roc_curve
)
from sklearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE

import joblib

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — edit these paths
# ─────────────────────────────────────────────────────────────────────────────
SWELL_CSV_PATH = "SWELLHRVData.csv"          # path to SWELL Kaggle CSV
WESAD_DATA_DIR = "WESAD/"                    # path to WESAD extracted folder
USE_DATASET    = "WESAD"                     # "SWELL" or "WESAD"
OUTPUT_DIR     = "model_output/"             # where model files are saved
ECG_SAMPLE_RATE = 700                        # Hz (WESAD) or 256 (your AD8232)
RANDOM_STATE   = 42


# ─────────────────────────────────────────────────────────────────────────────
# FEATURE EXTRACTION FROM RAW ECG SIGNAL
# (Used for WESAD and for your live Flask endpoint)
# ─────────────────────────────────────────────────────────────────────────────
def bandpass_filter(ecg_signal, lowcut=0.5, highcut=40.0, fs=700, order=4):
    """Bandpass filter to clean ECG signal."""
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = signal.butter(order, [low, high], btype='band')
    return signal.filtfilt(b, a, ecg_signal)


def detect_r_peaks(ecg_signal, fs=700):
    """
    Pan-Tompkins inspired R-peak detection.
    Returns array of R-peak indices.
    """
    # Derivative
    diff_ecg = np.diff(ecg_signal)
    # Square
    squared = diff_ecg ** 2
    # Moving window integration (150ms window)
    window_size = int(0.15 * fs)
    integrated = np.convolve(squared, np.ones(window_size) / window_size, mode='same')

    # Find peaks with minimum distance of 200ms (max 300 BPM)
    min_distance = int(0.2 * fs)
    threshold = np.mean(integrated) + 0.5 * np.std(integrated)

    peaks = []
    i = 0
    while i < len(integrated):
        if integrated[i] > threshold:
            # Find local max in this region
            start = i
            while i < len(integrated) and integrated[i] > threshold:
                i += 1
            end = i
            peak_idx = start + np.argmax(integrated[start:end])
            if not peaks or (peak_idx - peaks[-1]) >= min_distance:
                peaks.append(peak_idx)
        i += 1
    return np.array(peaks)


def compute_hrv_features(rr_intervals_ms):
    """
    Compute time-domain and frequency-domain HRV features from RR intervals.
    These are the exact features your Flask endpoint will compute in real-time.

    Parameters:
        rr_intervals_ms: array of RR intervals in milliseconds

    Returns:
        dict of features
    """
    if len(rr_intervals_ms) < 4:
        return None

    rr = np.array(rr_intervals_ms, dtype=float)

    # ── Time Domain Features ──────────────────────────────────────────────
    mean_rr   = np.mean(rr)
    sdnn      = np.std(rr)                                   # SDNN
    rmssd     = np.sqrt(np.mean(np.diff(rr) ** 2))          # RMSSD
    nn50      = np.sum(np.abs(np.diff(rr)) > 50)            # NN50
    pnn50     = (nn50 / len(rr)) * 100                      # pNN50
    mean_hr   = 60000.0 / mean_rr                           # Heart rate BPM
    sdsd      = np.std(np.diff(rr))                         # SDSD
    cv_rr     = (sdnn / mean_rr) * 100                      # Coefficient of variation

    # ── Frequency Domain Features (Welch PSD) ────────────────────────────
    # Interpolate RR to evenly sampled signal at 4 Hz
    try:
        rr_times = np.cumsum(rr) / 1000.0   # cumulative time in seconds
        interp_fs = 4.0
        t_interp = np.arange(rr_times[0], rr_times[-1], 1.0 / interp_fs)
        rr_interp = np.interp(t_interp, rr_times, rr)

        # Welch PSD
        freqs, psd = signal.welch(rr_interp, fs=interp_fs, nperseg=min(len(rr_interp), 256))

        # Frequency bands (Hz)
        vlf_band = (0.003, 0.04)
        lf_band  = (0.04,  0.15)
        hf_band  = (0.15,  0.40)

        def band_power(freqs, psd, low, high):
            idx = np.where((freqs >= low) & (freqs < high))[0]
            return np.trapz(psd[idx], freqs[idx]) if len(idx) > 0 else 0.0

        vlf_power = band_power(freqs, psd, *vlf_band)
        lf_power  = band_power(freqs, psd, *lf_band)
        hf_power  = band_power(freqs, psd, *hf_band)
        total_power = vlf_power + lf_power + hf_power

        lf_hf_ratio = lf_power / (hf_power + 1e-10)
        lf_norm     = lf_power / (lf_power + hf_power + 1e-10) * 100
        hf_norm     = hf_power / (lf_power + hf_power + 1e-10) * 100

    except Exception:
        lf_power = hf_power = vlf_power = total_power = 0.0
        lf_hf_ratio = lf_norm = hf_norm = 0.0

    # ── Non-linear Features ───────────────────────────────────────────────
    sd1 = np.sqrt(0.5) * np.std(np.diff(rr))    # Poincaré SD1
    sd2 = np.sqrt(2 * sdnn**2 - 0.5 * np.std(np.diff(rr))**2)  # Poincaré SD2
    sd1_sd2_ratio = sd1 / (sd2 + 1e-10)

    return {
        # Time domain
        "mean_rr":      mean_rr,
        "sdnn":         sdnn,
        "rmssd":        rmssd,
        "nn50":         nn50,
        "pnn50":        pnn50,
        "mean_hr":      mean_hr,
        "sdsd":         sdsd,
        "cv_rr":        cv_rr,
        # Frequency domain
        "vlf_power":    vlf_power,
        "lf_power":     lf_power,
        "hf_power":     hf_power,
        "total_power":  total_power,
        "lf_hf_ratio":  lf_hf_ratio,
        "lf_norm":      lf_norm,
        "hf_norm":      hf_norm,
        # Non-linear
        "sd1":          sd1,
        "sd2":          sd2,
        "sd1_sd2_ratio": sd1_sd2_ratio,
    }


def extract_features_from_ecg_window(ecg_window, fs=700, spo2=98.0):
    """
    Full pipeline: raw ECG window → feature dict.
    This is what Flask calls for every incoming ESP32 packet.

    Parameters:
        ecg_window : numpy array of raw ECG samples (e.g., 10s window)
        fs         : sampling rate
        spo2       : SpO2 value from MAX30102

    Returns:
        feature dict ready for model.predict()
    """
    # 1. Filter
    ecg_clean = bandpass_filter(ecg_window, fs=fs)

    # 2. Detect R-peaks
    r_peaks = detect_r_peaks(ecg_clean, fs=fs)

    if len(r_peaks) < 4:
        return None

    # 3. Compute RR intervals (ms)
    rr_intervals = np.diff(r_peaks) / fs * 1000.0

    # 4. Remove physiologically impossible RR intervals (< 300ms or > 2000ms)
    rr_intervals = rr_intervals[(rr_intervals > 300) & (rr_intervals < 2000)]

    if len(rr_intervals) < 3:
        return None

    # 5. HRV features
    features = compute_hrv_features(rr_intervals)
    if features is None:
        return None

    # 6. Add SpO2 from MAX30102
    features["spo2"] = spo2

    return features


# ─────────────────────────────────────────────────────────────────────────────
# DATASET LOADING
# ─────────────────────────────────────────────────────────────────────────────
def load_swell_dataset(csv_path):
    """
    Load the SWELL-HRV Kaggle dataset.
    Already has extracted HRV features — no raw signal processing needed.

    Download: https://www.kaggle.com/datasets/qiriro/swell-heart-rate-variability-hrv
    """
    print(f"\n[1/6] Loading SWELL dataset from: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"      Raw shape: {df.shape}")
    print(f"      Columns: {list(df.columns[:10])}...")

    # SWELL label column is 'condition': 'no stress', 'time pressure', 'interruption'
    # Binarize: stress = any non-baseline condition
    label_col = None
    for c in df.columns:
        if 'condition' in c.lower() or 'label' in c.lower() or 'stress' in c.lower():
            label_col = c
            break

    if label_col is None:
        # Fallback: last column
        label_col = df.columns[-1]
        print(f"      ⚠️  Auto-detected label column: {label_col}")
    else:
        print(f"      Label column: {label_col}")

    print(f"      Label distribution:\n{df[label_col].value_counts()}")

    # Encode labels → binary (0=no stress, 1=stress)
    df["stress_label"] = df[label_col].apply(
        lambda x: 0 if str(x).strip().lower() in ["no stress", "0", "baseline", "neutral"] else 1
    )

    # Drop non-numeric and label columns
    drop_cols = [label_col, "stress_label"]
    feature_cols = [c for c in df.columns if c not in drop_cols
                    and df[c].dtype in [np.float64, np.float32, np.int64, np.int32]]

    X = df[feature_cols].copy()
    y = df["stress_label"].copy()

    # Clean: drop columns with >30% missing
    X = X.dropna(axis=1, thresh=int(0.7 * len(X)))
    X = X.fillna(X.median())

    print(f"      Features: {X.shape[1]}, Samples: {len(X)}")
    print(f"      Stress distribution: {y.value_counts().to_dict()}")

    return X, y, list(X.columns)


def load_wesad_subject(subject_path, subject_id):
    """
    Load one WESAD subject's data (.pkl file) and extract features.
    WESAD labels: 1=baseline, 2=stress, 3=amusement, 0/4=other
    """
    import pickle as pkl
    with open(subject_path, 'rb') as f:
        data = pkl.load(f, encoding='latin1')

    # Chest ECG at 700 Hz
    ecg   = data['signal']['chest']['ECG'].flatten()
    labels = data['label']

    # Only keep baseline (1) and stress (2)
    valid_mask = np.isin(labels, [1, 2])
    ecg_valid   = ecg[valid_mask]
    labels_valid = labels[valid_mask]

    # Binary: stress=1, baseline=0
    binary_labels = (labels_valid == 2).astype(int)

    # Sliding window: 60s windows, 30s step
    fs = 700
    window_samples = 60 * fs
    step_samples   = 30 * fs

    feature_rows = []
    label_rows   = []

    for start in range(0, len(ecg_valid) - window_samples, step_samples):
        window = ecg_valid[start: start + window_samples]
        # Majority vote label for this window
        window_label = int(np.round(np.mean(binary_labels[start: start + window_samples])))

        # SpO2 placeholder (WESAD doesn't have SpO2; use 98.0 for training)
        feats = extract_features_from_ecg_window(window, fs=fs, spo2=98.0)
        if feats is not None:
            feature_rows.append(feats)
            label_rows.append(window_label)

    print(f"      Subject {subject_id}: {len(feature_rows)} windows extracted")
    return feature_rows, label_rows


def load_wesad_dataset(wesad_dir):
    """
    Load all WESAD subjects and combine into a single DataFrame.
    """
    print(f"\n[1/6] Loading WESAD dataset from: {wesad_dir}")
    subjects = [d for d in os.listdir(wesad_dir) if d.startswith('S')]

    all_features = []
    all_labels   = []

    for subject in sorted(subjects):
        pkl_path = os.path.join(wesad_dir, subject, f"{subject}.pkl")
        if os.path.exists(pkl_path):
            feats, labels = load_wesad_subject(pkl_path, subject)
            all_features.extend(feats)
            all_labels.extend(labels)

    df = pd.DataFrame(all_features)
    y  = pd.Series(all_labels)

    print(f"      Total windows: {len(df)}")
    print(f"      Stress distribution: {y.value_counts().to_dict()}")

    return df, y, list(df.columns)


# ─────────────────────────────────────────────────────────────────────────────
# TRAINING PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def train_and_evaluate(X, y, feature_names):
    """Full training pipeline: preprocess → SMOTE → train → evaluate → export."""

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Step 2: Train/test split ──────────────────────────────────────────
    print("\n[2/6] Splitting data (80/20 stratified)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )
    print(f"      Train: {len(X_train)} | Test: {len(X_test)}")

    # ── Step 3: Scale features ────────────────────────────────────────────
    print("\n[3/6] Scaling features (StandardScaler)...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # ── Step 3b: Handle class imbalance with SMOTE ────────────────────────
    print("      Applying SMOTE for class balancing...")
    smote = SMOTE(random_state=RANDOM_STATE)
    X_train_balanced, y_train_balanced = smote.fit_resample(X_train_scaled, y_train)
    print(f"      After SMOTE — {dict(zip(*np.unique(y_train_balanced, return_counts=True)))}")

    # ── Step 4: Hyperparameter tuning (Random Forest) ────────────────────
    print("\n[4/6] Tuning Random Forest (GridSearchCV)...")
    rf_param_grid = {
        'n_estimators': [100, 200, 300],
        'max_depth':    [None, 10, 20],
        'min_samples_split': [2, 5],
        'min_samples_leaf':  [1, 2],
    }
    rf_base = RandomForestClassifier(random_state=RANDOM_STATE, n_jobs=-1)
    rf_grid = GridSearchCV(
        rf_base, rf_param_grid,
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE),
        scoring='f1', n_jobs=-1, verbose=0
    )
    rf_grid.fit(X_train_balanced, y_train_balanced)
    best_rf = rf_grid.best_estimator_
    print(f"      Best RF params: {rf_grid.best_params_}")

    # ── Step 5: Compare multiple models ──────────────────────────────────
    print("\n[5/6] Comparing classifiers (5-fold CV)...")
    models = {
        "Random Forest (tuned)": best_rf,
        "Gradient Boosting":     GradientBoostingClassifier(n_estimators=200, random_state=RANDOM_STATE),
        "SVM (RBF)":             SVC(kernel='rbf', probability=True, random_state=RANDOM_STATE),
        "KNN":                   KNeighborsClassifier(n_neighbors=5),
        "Logistic Regression":   LogisticRegression(max_iter=1000, random_state=RANDOM_STATE),
    }

    cv_results = {}
    for name, model in models.items():
        scores = cross_val_score(
            model, X_train_balanced, y_train_balanced,
            cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE),
            scoring='f1', n_jobs=-1
        )
        cv_results[name] = scores
        print(f"      {name:30s} F1: {scores.mean():.4f} ± {scores.std():.4f}")

    # ── Train best model (Random Forest) on full training set ────────────
    print("\n      Training final Random Forest on full training data...")
    best_rf.fit(X_train_balanced, y_train_balanced)

    # ── Step 6: Evaluate on test set ──────────────────────────────────────
    print("\n[6/6] Evaluating on held-out test set...")
    y_pred      = best_rf.predict(X_test_scaled)
    y_pred_prob = best_rf.predict_proba(X_test_scaled)[:, 1]

    print(f"\n{'='*60}")
    print("FINAL TEST SET RESULTS")
    print(f"{'='*60}")
    print(f"Accuracy : {accuracy_score(y_test, y_pred):.4f}")
    print(f"ROC-AUC  : {roc_auc_score(y_test, y_pred_prob):.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["No Stress", "Stress"]))

    # ── Feature Importance ────────────────────────────────────────────────
    importances = pd.Series(best_rf.feature_importances_, index=feature_names)
    top_features = importances.nlargest(15)
    print("\nTop 15 Most Important Features:")
    print(top_features.to_string())

    # ── Save plots ────────────────────────────────────────────────────────
    _save_evaluation_plots(
        y_test, y_pred, y_pred_prob,
        importances, cv_results, feature_names
    )

    # ── Export model artifacts ────────────────────────────────────────────
    _export_model(best_rf, scaler, feature_names)

    return best_rf, scaler, feature_names


def _save_evaluation_plots(y_test, y_pred, y_pred_prob, importances, cv_results, feature_names):
    """Save confusion matrix, ROC curve, feature importance, and CV comparison."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Stress Detection Model Evaluation", fontsize=16, fontweight='bold')

    # 1. Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[0, 0],
                xticklabels=["No Stress", "Stress"],
                yticklabels=["No Stress", "Stress"])
    axes[0, 0].set_title("Confusion Matrix")
    axes[0, 0].set_ylabel("True Label")
    axes[0, 0].set_xlabel("Predicted Label")

    # 2. ROC curve
    fpr, tpr, _ = roc_curve(y_test, y_pred_prob)
    auc = roc_auc_score(y_test, y_pred_prob)
    axes[0, 1].plot(fpr, tpr, color='steelblue', lw=2, label=f'ROC (AUC = {auc:.3f})')
    axes[0, 1].plot([0, 1], [0, 1], 'k--', lw=1)
    axes[0, 1].set_xlabel("False Positive Rate")
    axes[0, 1].set_ylabel("True Positive Rate")
    axes[0, 1].set_title("ROC Curve")
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)

    # 3. Feature importance (top 15)
    top_feat = importances.nlargest(15)
    top_feat.plot(kind='barh', ax=axes[1, 0], color='steelblue')
    axes[1, 0].set_title("Top 15 Feature Importances")
    axes[1, 0].set_xlabel("Importance")
    axes[1, 0].invert_yaxis()

    # 4. Cross-validation F1 comparison
    model_names = list(cv_results.keys())
    means = [cv_results[m].mean() for m in model_names]
    stds  = [cv_results[m].std()  for m in model_names]
    short_names = [n.split('(')[0].strip() for n in model_names]
    axes[1, 1].barh(short_names, means, xerr=stds, color='coral', capsize=5)
    axes[1, 1].set_xlabel("F1 Score")
    axes[1, 1].set_title("5-Fold CV F1 Comparison")
    axes[1, 1].set_xlim(0, 1.1)
    axes[1, 1].grid(True, alpha=0.3, axis='x')

    plt.tight_layout()
    plot_path = os.path.join(OUTPUT_DIR, "evaluation_plots.png")
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"\n      Plots saved → {plot_path}")
    plt.close()


def _export_model(model, scaler, feature_names):
    """Export model, scaler, and feature names for Flask to load."""
    model_path   = os.path.join(OUTPUT_DIR, "stress_model.pkl")
    scaler_path  = os.path.join(OUTPUT_DIR, "scaler.pkl")
    features_path = os.path.join(OUTPUT_DIR, "feature_names.pkl")

    joblib.dump(model,         model_path)
    joblib.dump(scaler,        scaler_path)
    joblib.dump(feature_names, features_path)

    print(f"\n✅ Model exported:")
    print(f"   → {model_path}")
    print(f"   → {scaler_path}")
    print(f"   → {features_path}")
    print(f"\n   Load in Flask with:")
    print(f"     model    = joblib.load('{model_path}')")
    print(f"     scaler   = joblib.load('{scaler_path}')")
    print(f"     features = joblib.load('{features_path}')")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  STRESS DETECTION ML TRAINING PIPELINE")
    print("  MAX30102 + AD8232 → ESP32 → Flask → React")
    print("=" * 60)

    # Load dataset
    if USE_DATASET == "SWELL":
        if not os.path.exists(SWELL_CSV_PATH):
            print(f"\n❌ SWELL CSV not found at: {SWELL_CSV_PATH}")
            print("   Download from: https://www.kaggle.com/datasets/qiriro/swell-heart-rate-variability-hrv")
            print("   Then set SWELL_CSV_PATH at the top of this script.\n")
            return
        X, y, feature_names = load_swell_dataset(SWELL_CSV_PATH)

    elif USE_DATASET == "WESAD":
        if not os.path.exists(WESAD_DATA_DIR):
            print(f"\n❌ WESAD directory not found at: {WESAD_DATA_DIR}")
            print("   Download from: https://archive.ics.uci.edu/dataset/465/wesad")
            print("   Then set WESAD_DATA_DIR at the top of this script.\n")
            return
        X, y, feature_names = load_wesad_dataset(WESAD_DATA_DIR)

    else:
        print(f"❌ Unknown USE_DATASET value: {USE_DATASET}")
        return

    # Train, evaluate, export
    model, scaler, features = train_and_evaluate(X, y, feature_names)

    print("\n🎉 Training complete! Files saved to:", OUTPUT_DIR)
    print("   Next step: run flask_app.py to start your prediction server.\n")


if __name__ == "__main__":
    main()
