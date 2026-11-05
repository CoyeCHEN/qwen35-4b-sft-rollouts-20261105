"""Archive CI Trial evidence without following hostile test fixture symlinks."""

import argparse
import os
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def collect(root: Path, destination: Path, junit: list[Path]) -> int:
    count = 0
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for report in junit:
            if report.exists() and stat.S_ISREG(report.lstat().st_mode):
                archive.write(report, arcname=report.name)
                count += 1
        # upload-artifact's recursive glob follows links. The suite deliberately
        # creates cyclic links and non-regular files to test TaskClient safety.
        for folder, directories, files in os.walk(root, followlinks=False):
            parent = Path(folder)
            directories[:] = sorted(
                name
                for name in directories
                if not (parent / name).is_symlink()
                and not (parent / name).is_junction()
            )
            for name in sorted(files):
                path = parent / name
                relative = path.relative_to(root)
                if "trials" not in relative.parts:
                    continue
                trial_offset = relative.parts.index("trials") + 2
                tail = relative.parts[trial_offset:]
                if not tail or (
                    len(tail) > 1 and tail[0] not in {"agent", "verifier", "artifacts"}
                ):
                    continue
                if not stat.S_ISREG(path.lstat().st_mode):
                    continue
                archive.write(path, arcname="trials/" + relative.as_posix())
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("junit", nargs="*", type=Path)
    args = parser.parse_args()
    print(
        f"Archived {collect(args.root, args.destination, args.junit)} CI evidence files"
    )


if __name__ == "__main__":
    main()
