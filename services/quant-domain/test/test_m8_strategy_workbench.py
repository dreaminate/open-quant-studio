from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quant_domain.domain import QuantDomain
from quant_domain.project_archive import export_project_archive, import_project_archive
from quant_domain.strategy_library import load_strategy_catalog, render_strategy_notebook
from test_m1_http import HttpTestCase
from test_m2_session import PROJECT_ID, register_command
from test_m3_revisions import ROOT_REVISION_ID, create_revision_command


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_STRATEGY_IDS = [
    "a_share_trend_breakout",
    "a_share_research_short",
    "a_share_rotation",
    "crypto_trend",
    "crypto_mean_reversion",
    "crypto_breakout",
]


class M8StrategyWorkbenchHttpTest(HttpTestCase):
    def test_catalog_sources_and_deterministic_notebook_render_are_available(self) -> None:
        status, _, body = self.request("GET", "/v1/strategies")

        self.assertEqual(status, 200, body)
        strategies = json.loads(body)["strategies"]
        self.assertEqual(
            [strategy["strategy_id"] for strategy in strategies],
            EXPECTED_STRATEGY_IDS,
        )
        selected = strategies[0]
        source = (ROOT / selected["source"]).read_text()
        self.assertEqual(selected["source_body"], source)
        self.assertEqual(
            selected["source_sha256"], hashlib.sha256(source.encode()).hexdigest()
        )

        edited_source = source + "\n# Finalized from the M8 Code workbench.\n"
        request_body = json.dumps({"source": edited_source}).encode()
        renders = []
        for _ in range(2):
            status, _, body = self.request(
                "POST",
                f"/v1/strategies/{selected['strategy_id']}/notebook",
                body=request_body,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 200, body)
            renders.append(json.loads(body))

        self.assertEqual(renders[0], renders[1])
        rendered = renders[0]
        self.assertEqual(rendered["strategy_id"], selected["strategy_id"])
        self.assertEqual(rendered["file_name"], "strategy.ipynb")
        self.assertEqual(
            rendered["sha256"],
            hashlib.sha256(rendered["body"].encode()).hexdigest(),
        )
        notebook = json.loads(rendered["body"])
        self.assertEqual(notebook["nbformat"], 4)
        self.assertEqual(
            notebook["metadata"]["oqs"]["source_sha256"],
            hashlib.sha256(edited_source.encode()).hexdigest(),
        )
        self.assertEqual(
            next(
                cell["source"]
                for cell in notebook["cells"]
                if cell["metadata"].get("oqs", {}).get("role")
                == "authoritative_source"
            ),
            edited_source,
        )


class M8StrategyWorkbenchArchiveTest(unittest.TestCase):
    def test_finalized_source_and_notebook_survive_project_archive_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            domain = QuantDomain(temporary_root / "source")
            domain.submit_command(register_command())
            strategy = load_strategy_catalog()["strategies"][0]
            source = strategy["source_body"]
            notebook = render_strategy_notebook(strategy["strategy_id"], source)["body"]
            files = [
                (
                    "strategy.py",
                    source.encode(),
                    "81818181-8181-4181-8181-818181818181",
                ),
                (
                    "strategy.ipynb",
                    notebook.encode(),
                    "82828282-8282-4282-8282-828282828282",
                ),
            ]
            for _, body, _ in files:
                domain.store_blob(hashlib.sha256(body).hexdigest(), body)
            domain.submit_command(
                create_revision_command(
                    command_id="83838383-8383-4383-8383-838383838383",
                    revision_id=ROOT_REVISION_ID,
                    files=files,
                )
            )
            before = domain.revision(PROJECT_ID, ROOT_REVISION_ID)
            archive_path = temporary_root / "m8.oqs.zip"
            export_project_archive(
                domain,
                project_id=PROJECT_ID,
                archive_path=archive_path,
            )

            restored = QuantDomain(temporary_root / "restored")
            import_project_archive(
                restored,
                archive_path,
                expected_project_id=PROJECT_ID,
            )
            after = restored.revision(PROJECT_ID, ROOT_REVISION_ID)

        self.assertEqual(after, before)
        self.assertEqual(
            [file["path"] for file in after["files"]],
            ["strategy.ipynb", "strategy.py"],
        )
        self.assertEqual(
            {file["path"]: file["sha256"] for file in after["files"]},
            {
                "strategy.py": hashlib.sha256(source.encode()).hexdigest(),
                "strategy.ipynb": hashlib.sha256(notebook.encode()).hexdigest(),
            },
        )
