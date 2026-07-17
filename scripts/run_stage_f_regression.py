"""Run the Stage F role matrix and deterministic product demo flows."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_TESTS = ["tests/test_stage_f_product_regression.py"]
DEMO_TESTS = [
    "tests/test_course_space.py::test_announcement_notification_and_course_resource_are_member_scoped",
    "tests/test_assignment_workflow.py::test_stage2_assignment_submit_return_resubmit_grade_publish_flow",
    "tests/test_stage_d.py::test_stage_d_attendance_is_session_based_correctable_and_scoped",
    "tests/test_stage_d.py::test_stage_d_questions_support_privacy_reply_followup_and_notification",
    "tests/test_support_workflow.py::test_counselor_complete_support_case_flow_and_share_to_student",
    "tests/test_stage_e.py::test_stage_e_teacher_college_and_academic_workflow",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 F：在独立临时数据库中运行六角色产品回归和演示链路。")
    parser.add_argument("--full", action="store_true", help="运行整个测试套件，而不仅是阶段 F 与演示链路。")
    parser.add_argument("--verbose", action="store_true", help="显示每个场景名称。")
    args = parser.parse_args()
    selected = [] if args.full else PRODUCT_TESTS + DEMO_TESTS
    with tempfile.TemporaryDirectory(prefix="nl2sql-stage-f-") as temp_dir:
        command = [sys.executable, "-m", "pytest", "-v" if args.verbose else "-q", *selected, f"--basetemp={Path(temp_dir) / 'pytest'}"]
        print("阶段 F 回归使用临时运行目录，不会写入共享演示数据库。")
        return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
