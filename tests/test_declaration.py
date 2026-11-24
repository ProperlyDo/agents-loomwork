from __future__ import annotations

from loomwork.errors import LoomError
from loomwork.targets.declaration import Declaration
from tests.fixtures import (
    SandboxTestCase,
    make_target_dir,
)


class DeclarationTests(SandboxTestCase):
    def test_a_broken_declaration_fails_in_one_line(self) -> None:
        target_dir = make_target_dir(self.root)
        (target_dir / Declaration.FILE_NAME).write_text("source = \n")
        with self.assertRaises(LoomError) as refused:
            Declaration.read(target_dir)
        self.assertEqual(len(str(refused.exception).splitlines()), 1)
