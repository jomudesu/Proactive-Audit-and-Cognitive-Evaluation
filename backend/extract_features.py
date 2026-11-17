import pandas as pd
import numpy as np
import os
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..")) if os.path.basename(SCRIPT_DIR) == "backend" else SCRIPT_DIR

def compute_dwell_time(log_df):
    df = log_df.copy()
    df['match_idx'] = df.groupby(['event_type', 'key_category']).cumcount()
    presses = df[df['event_type'] == 'press']
    releases = df[df['event_type'] == 'release']
    
    merged = pd.merge(presses, releases, on=['key_category', 'match_idx'], suffixes=('_press', '_release'))
    merged = merged[merged['timestamp_ms_press'] < merged['timestamp_ms_release']]
    merged['dwell_time_ms'] = merged['timestamp_ms_release'] - merged['timestamp_ms_press']
    merged = merged[merged['dwell_time_ms'] < 3000]
    return merged['dwell_time_ms']

def compute_flight_time(log_df):
    release_times = log_df[log_df['event_type'] == 'release']['timestamp_ms'].values
    press_times = log_df[log_df['event_type'] == 'press']['timestamp_ms'].values
    
    flight_times = []
    for i in range(len(release_times) - 1):
        flight = press_times[i+1] - release_times[i]
        if 0 < flight < 5000:
            flight_times.append(flight)
    return pd.Series(flight_times)

def compute_iki_variance(log_df):
    """Calculates the variance of Inter-Keystroke Intervals (Press-to-Press)."""
    presses = log_df[log_df['event_type'] == 'press'].sort_values('timestamp_ms')
    if len(presses) < 2:
        return 0
    
    iki = presses['timestamp_ms'].diff()
    valid_iki = iki[(iki > 0) & (iki < 5000)] 
    
    if len(valid_iki) < 2:
        return 0
    return valid_iki.var()

def compute_overall_kpm(total_keystrokes, duration_seconds):
    """Calculates gross motor productivity (Keys per Minute)."""
    if duration_seconds <= 0:
        return 0
    return (total_keystrokes / duration_seconds) * 60

def compute_kpm_deviation(log_df):
    """Calculates the standard deviation of Keystrokes Per Minute across rolling 60-second blocks."""
    presses = log_df[log_df['event_type'] == 'press'].copy()
    if presses.empty:
        return 0
        
    start_time = presses['timestamp_ms'].min()
    presses['relative_time_ms'] = presses['timestamp_ms'] - start_time    
    presses['minute_bin'] = (presses['relative_time_ms'] // 60000).astype(int)
    kpm_counts = presses.groupby('minute_bin').size()
    
    if len(kpm_counts) > 1:
        return kpm_counts.std()
    return 0

def compute_backspace_frequency(log_df, total_duration_seconds):
    backspace_count = len(log_df[(log_df['event_type'] == 'press') & (log_df['key_category'] == 'BACKSPACE')])
    if total_duration_seconds <= 0:
        return 0
    return (backspace_count / total_duration_seconds) * 60

def extract_session_features(csv_path):
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"[ERROR] Could not read {os.path.basename(csv_path)}: {e}")
        return None
        
    if df.empty:
        return None
        
    filename = os.path.basename(csv_path)
    session_id = filename.replace("_keystrokes.csv", "")
    
    session_start = df['timestamp_ms'].min()
    session_end = df['timestamp_ms'].max()
    duration_seconds = (session_end - session_start) / 1000
    
    dwell_time_series = compute_dwell_time(df)
    flight_time_series = compute_flight_time(df)
    
    iki_var = compute_iki_variance(df)
    kpm_dev = compute_kpm_deviation(df)
    
    backspace_freq = compute_backspace_frequency(df, duration_seconds)
    total_backspaces = len(df[(df['event_type'] == 'press') & (df['key_category'] == 'BACKSPACE')])
    total_keystrokes = len(df[df['event_type'] == 'press'])
    
    overall_kpm = compute_overall_kpm(total_keystrokes, duration_seconds)
    
    return {
        'Session_ID': session_id,
        'Duration_Seconds': round(duration_seconds, 2),
        'IKI_Variance': round(iki_var, 2),
        'Overall_KPM': round(overall_kpm, 2),
        'KPM_Deviation': round(kpm_dev, 2),
        'Mean_Dwell_ms': round(dwell_time_series.mean(), 2) if not dwell_time_series.empty else 0,
        'Std_Dwell_ms': round(dwell_time_series.std(), 2) if not dwell_time_series.empty else 0,
        'Mean_Flight_ms': round(flight_time_series.mean(), 2) if not flight_time_series.empty else 0,
        'Std_Flight_ms': round(flight_time_series.std(), 2) if not flight_time_series.empty else 0,
        'Backspace_Per_Minute': round(backspace_freq, 2),
        'Total_Backspaces': total_backspaces,
        'Total_Keystrokes': total_keystrokes
    }

def process_all_keylogs():
    os.chdir(PROJECT_ROOT)
    
    keystroke_files = glob.glob("**/*_keystrokes.csv", recursive=True)
    
    if not keystroke_files:
        print(f"[SYSTEM] No keystroke logs found in {PROJECT_ROOT} or its subfolders.")
        return

    print(f"[SYSTEM] Found {len(keystroke_files)} keystroke logs across all folders. Extracting features...")
    
    all_features = []
    
    for file in keystroke_files:
        print(f"  -> Processing {file}...")
        features = extract_session_features(file)
        if features:
            all_features.append(features)
            
    if all_features:
        final_df = pd.DataFrame(all_features)
        output_file = "EXTRACTED_FEATURES.csv"
        final_df.to_csv(output_file, index=False)
        print(f"\n[SUCCESS] Extracted features saved to {os.path.join(PROJECT_ROOT, output_file)}")
    else:
        print("\n[WARNING] No valid features could be extracted.")

if __name__ == "__main__":
    process_all_keylogs()