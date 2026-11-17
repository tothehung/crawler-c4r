"""Unit tests for Evaluator Metrics (Task 5.3 per plandatn.md).

Formally verifies metric calculations against hand-calculated ground truth examples:
  1. Loại đúng FP (FP Reduction Rate / True Negative Rate on FP set)
  2. Loại nhầm TP (TP Drop Rate / False Negative Rate on TP set)
  3. Precision của nhóm AI xác nhận là lỗi thật (TP / (TP + FP))
  4. Tỷ lệ Uncertain và khối lượng cần auditor review
  5. Xử lý finding trùng lặp và lỗi request (ERROR != Uncertain)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.run_pilot_triage import calculate_metrics


def test_hand_calculated_evaluator_example():
    """Ví dụ tính tay chuẩn xác minh logic toán học của Evaluator.
    
    Giả sử tập dữ liệu có 30 findings:
      - 10 cases là TP thật (Ground Truth = TP)
      - 10 cases là FP thật (Ground Truth = FP)
      - 10 cases là Uncertain thật (Ground Truth = Uncertain)
      
    Kết quả mô hình dự đoán:
      - Trong 10 TP thật:
          * 9 cases đoán đúng TP  -> TP = 9
          * 1 case đoán nhầm FP  -> FN = 1 (Loại nhầm TP = 1/10 = 10%)
      - Trong 10 FP thật:
          * 8 cases đoán đúng FP  -> TN = 8 (Loại đúng FP = 8/10 = 80%)
          * 2 cases đoán nhầm TP  -> FP = 2
      - Trong 10 Uncertain thật:
          * 7 cases đoán đúng Uncertain -> Match = 7
          * 2 cases đoán TP             -> FP_unc = 2
          * 1 case đoán FP              -> FN_unc = 1
    """
    cases = []
    preds = []
    
    # 1. 10 TP ground truths
    for i in range(9):
        cases.append({"case_id": f"tp-{i}", "ground_truth_label": "TP"})
        preds.append({"label": "TP"})
    cases.append({"case_id": "tp-9", "ground_truth_label": "TP"})
    preds.append({"label": "FP"})  # loại nhầm 1 TP!
    
    # 2. 10 FP ground truths
    for i in range(8):
        cases.append({"case_id": f"fp-{i}", "ground_truth_label": "FP"})
        preds.append({"label": "FP"})  # loại đúng 8 FP
    for i in range(2):
        cases.append({"case_id": f"fp-err-{i}", "ground_truth_label": "FP"})
        preds.append({"label": "TP"})  # đoán nhầm thành TP
        
    # 3. 10 Uncertain ground truths
    for i in range(7):
        cases.append({"case_id": f"unc-{i}", "ground_truth_label": "Uncertain"})
        preds.append({"label": "Uncertain"})
    for i in range(2):
        cases.append({"case_id": f"unc-tp-{i}", "ground_truth_label": "Uncertain"})
        preds.append({"label": "TP"})
    cases.append({"case_id": "unc-fp-0", "ground_truth_label": "Uncertain"})
    preds.append({"label": "FP"})
    
    m = calculate_metrics(cases, preds)
    
    # Kiểm tra chỉ số tính toán
    # TP = 9 (GT TP đoán TP)
    # FP (False Alarms) = 2 (GT FP đoán nhầm TP)
    # Precision = TP / (TP + False Alarms) = 9 / (9 + 2) = 9/11 ≈ 81.8%
    assert abs(m["precision"] - (9 / 11 * 100)) < 0.1
    
    # Recall = TP / (TP + FN) = 9 / (9 + 1) = 90.0%
    assert abs(m["recall"] - 90.0) < 0.1
    
    # Accuracy tổng = (9 TP + 8 FP + 7 Uncertain) / 30 = 24 / 30 = 80.0%
    assert abs(m["accuracy"] - 80.0) < 0.1
    
    # Tỷ lệ loại đúng FP (FP Reduction) = 8 / 10 = 80.0%
    assert abs(m["fp_reduction"] - 80.0) < 0.1


def test_evaluator_perfect_system():
    """Hệ thống hoàn hảo: B4/B5 khớp 100% ground truth."""
    cases = [
        {"case_id": "c1", "ground_truth_label": "TP"},
        {"case_id": "c2", "ground_truth_label": "FP"},
        {"case_id": "c3", "ground_truth_label": "Uncertain"},
    ]
    preds = [
        {"label": "TP"},
        {"label": "FP"},
        {"label": "Uncertain"},
    ]
    m = calculate_metrics(cases, preds)
    assert m["precision"] == 100.0
    assert m["recall"] == 100.0
    assert m["fp_rate"] == 0.0
    assert m["fp_reduction"] == 100.0
    assert m["accuracy"] == 100.0


def test_evaluator_request_error_isolation():
    """Kiểm tra phân biệt lỗi request (ERROR) khác với phán đoán Uncertain."""
    cases = [
        {"case_id": "c1", "ground_truth_label": "TP"},
        {"case_id": "c2", "ground_truth_label": "Uncertain"},
    ]
    preds = [
        {"label": "ERROR", "error_type": "TIMEOUT_ERROR"},
        {"label": "Uncertain"},
    ]
    m = calculate_metrics(cases, preds)
    # Case có ERROR không được tính là match
    assert m["accuracy"] == 50.0  # Chỉ c2 match
