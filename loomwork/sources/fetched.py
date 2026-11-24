from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from loomwork import git, paths
from loomwork.output import info, warn
from loomwork.sources.catalog import Catalog
from loomwork.sources.manifest import Manifest
from loomwork.sources.source import Source
from loomwork.targets.declaration import Declaration

if TYPE_CHECKING:
    from pathlib import Path

    from loomwork.registry import Registry


class FetchedSources:
    """The sources loom fetched, as its registry records them: adding them, keeping them current, and reading them."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def add(self, location: str, pinned_to: tuple[Path, ...] = ()) -> str:
        """Fetch a source and every source it builds on, pin it to these config dirs, and return its key."""
        key = self._fetch_with_bases(location, {})
        for config_dir in pinned_to:
            self.registry.pin_source(config_dir, key)
        return key

    def add_declared(self, target_dir: Path) -> None:
        """Add each source the target dir declares that loom lacks, or whose working copy replaced its clone."""
        declaration = Declaration.read(target_dir)
        if declaration is None:
            return
        for declared in declaration.sources:
            # a relative path counts from the target dir, wherever loom happens to run from
            source = Source.of(paths.resolved_from(declared.source, target_dir))
            if source.needs_adding(self.registry.checkout_of(source.key)):
                self.add(source.location)

    def refresh(self, keys: list[str]) -> None:
        """Bring these sources up to date before anything is copied from them."""
        self.warn_about_gone(keys)
        repos: dict[Path, Source] = {}
        for key in keys:
            checkout = self.registry.checkout_of(key)
            if checkout is not None and checkout.is_dir():
                # once per repo: two sources in subdirectories of one clone would otherwise race for its lock
                repos.setdefault(git.root(checkout), Source.of(self.registry.source_of(key)))
        if not repos:
            return
        # concurrently, since each update is a network round trip
        with ThreadPoolExecutor(max_workers=len(repos)) as updating:
            attempts = {checkout: updating.submit(source.update, checkout) for checkout, source in repos.items()}
        for checkout, attempt in attempts.items():
            if not attempt.result():
                warn(f"could not update {checkout} — using it as it stands")

    def offered_by(self, location: str) -> Catalog:
        """What one source defines, for init to offer — added on the way, so wiring it later fetches nothing more."""
        return Catalog.of(self.registry.checkout_of(self.add(location)))

    def warn_about_gone(self, keys: list[str]) -> None:
        """Name each source no longer where it was added — the ones a target dir declares are fetched before this."""
        for key in keys:
            checkout = self.registry.checkout_of(key)
            if checkout is None or checkout.is_dir():
                continue
            warn(Source.of(self.registry.source_of(key)).gone_warning(checkout))

    def keys_of(self, config_dir: Path) -> list[str]:
        """The sources a config dir draws on: those pinned to it, then those its target dirs declare, each after its bases."""
        pinned = self.registry.sources_pinned_to(config_dir)
        return self._with_bases([*pinned, *self.registry.sources_declared_in(config_dir)])

    def declared_keys(self, target_dir: Path) -> list[str]:
        """The keys of the sources a target dir declares, each after what it builds on."""
        declaration = Declaration.read(target_dir)
        if declaration is None:
            return []
        declared = [Source.of(paths.resolved_from(entry.source, target_dir)).key for entry in declaration.sources]
        return self._with_bases(declared)

    def catalog_of(self, keys: list[str]) -> Catalog:
        return Catalog.of(*self._checkouts(keys))

    def _fetch_with_bases(self, location: str, fetched: dict[str, Path]) -> str:
        """Fetch a source and record it after what it builds on, returning its key."""
        source = Source.of(location)
        key = source.key
        # sources that build on each other in a loop stop at the first one met again
        if key in fetched:
            return key
        checkout = source.fetch()
        fetched[key] = checkout
        bases = [
            self._fetch_with_bases(paths.resolved_from(base, checkout), fetched)
            for base in Manifest.read(checkout).builds_on
        ]
        if self.registry.checkout_of(key) is None:
            info(f"added source {location}")
        self.registry.add_source(key, checkout, location, bases)
        return key

    def _checkouts(self, keys: list[str]) -> list[Path]:
        """Where each of these sources sits, leaving out keys loom never added."""
        located = [self.registry.checkout_of(key) for key in keys]
        return [checkout for checkout in located if checkout is not None]

    def _with_bases(self, keys: list[str]) -> list[str]:
        """These sources, each once and after what it builds on, so the source itself wins a name they share."""
        ordered: list[str] = []
        for key in keys:
            self._append_with_bases(key, ordered, visiting=set())
        return ordered

    def _append_with_bases(self, key: str, ordered: list[str], visiting: set[str]) -> None:
        # sources that build on each other in a loop stop at the first one met again
        if key in ordered or key in visiting:
            return
        visiting.add(key)
        for base in self.registry.bases_of(key):
            self._append_with_bases(base, ordered, visiting)
        ordered.append(key)
