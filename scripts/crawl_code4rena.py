from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.code4rena_client import Code4renaClient
from src.services.code4rena_service import (
    DEFAULT_CODE4RENA_CHECKPOINT_PATH,
    DEFAULT_CODE4RENA_JSONL_PATH,
    Code4renaExportService,
)


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run() -> None:
    parser = argparse.ArgumentParser(
        description="Bộ cào toàn diện dữ liệu kiểm toán từ Code4rena (code4rena.com).",
    )
    parser.add_argument(
        "--max-contests",
        type=int,
        default=None,
        help="Số lượng cuộc thi (contests) tối đa muốn cào trong lần này. Để trống nếu muốn cào toàn bộ.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CODE4RENA_JSONL_PATH,
        help=f"File lưu dữ liệu JSONL. Mặc định: {DEFAULT_CODE4RENA_JSONL_PATH}",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CODE4RENA_CHECKPOINT_PATH,
        help=f"File lưu tiến độ checkpoint. Mặc định: {DEFAULT_CODE4RENA_CHECKPOINT_PATH}",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Xóa file kết quả và checkpoint cũ, cào lại từ đầu.",
    )
    parser.add_argument(
        "--severities",
        type=str,
        default="all",
        help="Danh sách mức độ nghiêm trọng cần lấy (phân cách bằng dấu phẩy), ví dụ: 'HIGH,MEDIUM' hoặc 'all'. Mặc định: all",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Độ trễ (giây) giữa các lượt tải báo cáo để tránh quá tải server. Mặc định: 0.5s",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Bật log chi tiết (DEBUG).",
    )

    args = parser.parse_args()
    configure_logging(args.verbose)

    allowed_severities: set[str] | None = None
    if args.severities.strip().lower() != "all":
        allowed_severities = {
            s.strip().upper() for s in args.severities.split(",") if s.strip()
        }

    print("=" * 65)
    print("  BỘ CÀO DỮ LIỆU TOÀN DIỆN CODE4RENA (CODE4RENA.COM)")
    print(f"  - File xuất JSONL:    {args.output}")
    print(f"  - File Checkpoint:    {args.checkpoint}")
    print(f"  - Số contest tối đa:  {args.max_contests if args.max_contests else 'Toàn bộ (~412 contests)'}")
    print(f"  - Severities lọc:     {allowed_severities or 'Tất cả (HIGH, MEDIUM, LOW, INFO, GAS)'}")
    print(f"  - Chế độ cào:         {'Cào lại từ đầu (RESET)' if args.reset else 'Tiếp tục từ Checkpoint (RESUME)'}")
    print("=" * 65)

    with Code4renaClient(request_delay_seconds=args.delay) as client:
        service = Code4renaExportService(
            client=client,
            output_path=args.output,
            checkpoint_path=args.checkpoint,
        )

        result = service.export_all(
            max_contests=args.max_contests,
            resume=not args.reset,
            allowed_severities=allowed_severities,
        )

    print("\n" + "=" * 65)
    print("  KẾT QUẢ CÀO DỮ LIỆU:")
    print(f"  - Số contest đã xử lý đợt này: {result.contests_processed}")
    print(f"  - Số findings ghi nhận đợt này: {result.records_written}")
    print(f"  - Trạng thái hoàn thành toàn bộ: {'ĐÃ XONG HẾT' if result.completed else 'CHƯA HẾT (tiếp tục trong lần sau)'}")
    print(f"  - Vị trí file: {result.output_path.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    run()
