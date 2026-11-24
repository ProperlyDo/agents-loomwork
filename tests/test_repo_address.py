from __future__ import annotations

from loomwork.sources.repo_address import RepoAddress
from tests.fixtures import SandboxTestCase


class SourceSpellingTests(SandboxTestCase):
    """However a clone url was copied, it names the same repo."""

    def test_every_form_of_the_url_reduces_to_host_owner_repo(self) -> None:
        for url in (
            "forge.test/acme/agent-rules",
            "https://forge.test/acme/agent-rules",
            "git@forge.test:acme/agent-rules.git",
            "ssh://git@forge.test/acme/agent-rules/",
            "ssh://git@forge.test:2222/acme/agent-rules.git",
            "https://user:token@forge.test/acme/agent-rules",
        ):
            self.assertEqual(RepoAddress.parse(url), RepoAddress("forge.test", "acme", "agent-rules"), url)

    def test_a_subdirectory_survives_the_scheme(self) -> None:
        self.assertEqual(
            RepoAddress.parse("ssh://git@forge.test/group/repo/agents"),
            RepoAddress("forge.test", "group", "repo", "agents"),
        )

    def test_something_that_names_no_repo_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RepoAddress.parse("nonsense")
