"""命令行入口：ygc <command>。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ygc",
        description="燕云十六声装备毕业度计算器：拍照识别词条 -> 按流派权重算毕业度",
    )
    sub = p.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import-build", help="从毕业率计算器 xlsx 导入流派数据（文件或目录）")
    imp.add_argument("path", help="计算器 xlsx 路径或所在目录")
    imp.add_argument("--out", default="builds", help="流派数据输出目录")

    rec = sub.add_parser("recognize", help="只识别不评分：打印图片里的装备词条")
    rec.add_argument("images", nargs="+", help="图片路径")

    sc = sub.add_parser("score", help="识别并计算毕业度")
    sc.add_argument("images", nargs="+", help="图片路径（可多张）")
    sc.add_argument("--build", default=None, help="指定流派名（默认与所有已导入流派对比取最优）")
    sc.add_argument("--builds-dir", default="builds")
    sc.add_argument("--max-table", default=None, help="词条满值表路径（默认 data/affix_max.json）")
    sc.add_argument("--json-out", default=None, help="结果另存 JSON")

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "import-build":
        from .build_import import import_folder

        paths = import_folder(args.path, args.out)
        print(f"已导入 {len(paths)} 个流派 -> {args.out}/")
        for p in paths:
            data = json.loads(p.read_text(encoding="utf-8"))
            print(f"  {data['name']}: 关注 {len(data['affix_weights'])} 类词条（{Path(p).name}）")

    elif args.command == "recognize":
        from .ocr import recognize

        for img in args.images:
            piece = recognize(img)
            print(f"\n◆ {img}")
            print(f"   {piece.name} {piece.tier} {piece.set_name} 造诣{piece.craft_score}")
            for a in piece.affixes:
                unit = "%" if a.unit == "percent" else ""
                marks = ("[转]" if a.converted else "") + ("荐" if a.recommended else "")
                flag = "" if a.known else "  (未识别词条名)"
                print(f"   {a.name}: {a.value}{unit} {marks}{flag}")

    elif args.command == "score":
        from .ocr import recognize
        from .scoring import (compare_builds, format_report, load_builds,
                              load_max_table, score_piece)

        max_table = load_max_table(args.max_table)
        builds = load_builds(args.builds_dir)
        if args.build:
            if args.build not in builds:
                sys.exit(f"流派 {args.build} 未导入。已导入: {', '.join(builds)}")
            builds = {args.build: builds[args.build]}

        results = []
        for img in args.images:
            piece = recognize(img)
            if args.build:
                sc = score_piece(piece, builds[args.build], max_table)
                print(format_report(sc) + "\n")
                results.append({"image": img, "build": args.build, "score": sc.score,
                                "grade": sc.grade})
            else:
                ranked = compare_builds(piece, builds, max_table)
                if not ranked:
                    continue
                best = ranked[0]
                print(format_report(best) + "\n")
                others = "  ".join(
                    f"{s.build} {s.score if s.score is not None else '—'}"
                    for s in ranked[1:] if s.score is not None
                )
                if others:
                    print(f"   其他流派: {others}\n")
                results.append({"image": img, "best_build": best.build,
                                "score": best.score, "grade": best.grade})

        if args.json_out:
            out = Path(args.json_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"结果已保存: {out}")


if __name__ == "__main__":
    main()
