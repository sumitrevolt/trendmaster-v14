"""
Hyperparameter Optimizer for AI Trading Agents
===============================================
Reads agent_training_data.json (generated via backtesting),
runs GridSearchCV on RandomForest to find optimal technical thresholds,
and saves them to optimized_thresholds.json for local agent execution.
"""

import json
import os
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.metrics import classification_report, accuracy_score

_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINING_FILE = os.path.join(_DIR, "agent_training_data.json")
OUTPUT_FILE = os.path.join(_DIR, "optimized_thresholds.json")

def main():
    print("Loading training data...")
    if not os.path.exists(TRAINING_FILE):
        print(f"File not found: {TRAINING_FILE}")
        return

    with open(TRAINING_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    trades = data.get("trades", [])
    print(f"Loaded {len(trades)} trades.")
    
    if len(trades) < 100:
        print("Insufficient trades to perform machine learning optimization. Need at least 100.")
        return

    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(trades)
    
    # Target label: 1 if WIN, 0 if LOSS
    if "outcome" not in df.columns:
        print("No outcome column found in training data.")
        return
    
    df["y"] = df["outcome"].apply(lambda x: 1 if x == "WIN" else 0)
    
    # Features to rely on exclusively (No external API elements)
    features_cols = ["score", "rsi", "adx", "hour_utc", "confidence"]
    
    # Ensure they exist and handle missing values
    for col in features_cols:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    X = df[features_cols]
    y = df["y"]
    
    print("Splitting data into train/test sets...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    print("Training RandomForest Local AI...")
    
    # We want a shallow tree so we can extract readable thresholds later if needed,
    # or just use the model to predict.
    param_grid = {
        'n_estimators': [50, 100, 200],
        'max_depth': [3, 5, 10],
        'min_samples_split': [10, 50, 100]
    }
    
    rf = RandomForestClassifier(random_state=42, class_weight="balanced")
    grid_search = GridSearchCV(estimator=rf, param_grid=param_grid, cv=3, scoring='accuracy', n_jobs=-1, verbose=1)
    
    print("Starting Grid Search (this may take a minute)...")
    grid_search.fit(X_train, y_train)
    
    best_model = grid_search.best_estimator_
    best_params = grid_search.best_params_
    
    print(f"\nBest Parameters Found: {best_params}")
    
    y_pred = best_model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\nTest Set Accuracy: {acc * 100:.2f}%")
    print(classification_report(y_test, y_pred))

    # Exporting simplistic thresholds based on features
    # Extract feature importances
    importances = best_model.feature_importances_
    feat_imp = dict(zip(features_cols, importances))
    print("\nFeature Importance:")
    for f_name, f_imp in sorted(feat_imp.items(), key=lambda x: x[1], reverse=True):
        print(f"  {f_name}: {f_imp*100:.1f}%")

    # Determine best simplistic min/max thresholds by looking at successful trades predicted by local AI
    df_test = X_test.copy()
    df_test['true_y'] = y_test
    df_test['pred_y'] = y_pred
    
    # High probability winning conditions
    winners = df_test[(df_test['true_y'] == 1) & (df_test['pred_y'] == 1)]
    
    if len(winners) > 0:
        optimal_settings = {
            "last_trained_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "accuracy": round(acc * 100, 2),
            "model": "RandomForestClassifier",
            "hyperparameters": best_params,
            "threshold_guides": {
                "min_score": float(winners['score'].quantile(0.1)),
                "optimal_rsi_min": float(winners['rsi'].quantile(0.1)),
                "optimal_rsi_max": float(winners['rsi'].quantile(0.9)),
                "min_adx_trend": float(winners['adx'].quantile(0.2)),
                "min_confidence": float(winners['confidence'].quantile(0.15))
            },
            "feature_importance": feat_imp
        }
    else:
        optimal_settings = {"error": "Model could not confidently predict winners."}

    print(f"\nExporting Local AI Optimization guide to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(optimal_settings, f, indent=4)
        
    print("Done. You can now inject these optimized thresholds into main.py or ai_swarm_main.py!")

if __name__ == "__main__":
    main()
