from unittest.mock import patch

# a backstop: a git call no test patched fails loudly, so nothing reaches a remote or a real repo
patch("loomwork.git.run", side_effect=RuntimeError("git ran during a test — patch the git function it needs")).start()
