"""Which commit is this app running? Read from the checkout's .git (no git
binary needed). Shown as a tiny footer so the keep-awake probe can detect a
deploy that silently stopped following main (happened 2026-09-21: Streamlit
Cloud applied pushes up to 13:35 UTC and ignored the next ten)."""
from pathlib import Path


def get_build_sha() -> str | None:
    root = Path(__file__).resolve().parent.parent
    git = root / ".git"
    try:
        if git.is_file():  # worktree pointer: "gitdir: /path"
            git = Path(git.read_text().split(":", 1)[1].strip())
        head = (git / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            ref_file = git / ref
            if ref_file.exists():
                return ref_file.read_text().strip()
            packed = git / "packed-refs"
            if packed.exists():
                for line in packed.read_text().splitlines():
                    if line.endswith(" " + ref):
                        return line.split(" ", 1)[0]
            return None
        return head
    except Exception:
        return None
