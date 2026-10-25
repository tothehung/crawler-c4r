"""W3GoAudit Engine Bridge — Connects Go Static Analysis Engine to Python AI Triage.

Integrates:
  - w3goaudit.exe scan (WQL template matching -> findings.json + authorization.json)
  - w3goaudit.exe extract bundle (AST-based LLM-ready context extraction)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("w3goaudit.engine_bridge")

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENGINE_PATH = ROOT / "w3goaudit-main" / "w3goaudit.exe"


class W3GoAuditEngineBridge:
    def __init__(self, engine_path: Optional[Path | str] = None):
        if engine_path:
            self.executable = Path(engine_path).resolve()
        else:
            env_path = os.getenv("W3GOAUDIT_ENGINE")
            self.executable = Path(env_path).resolve() if env_path else DEFAULT_ENGINE_PATH

        if not self.executable.exists():
            logger.warning("w3goaudit executable not found at %s", self.executable)

    def is_available(self) -> bool:
        return self.executable.exists() and os.access(self.executable, os.X_OK | os.R_OK)

    def run_scan(
        self,
        target_path: Path | str,
        output_dir: Optional[Path | str] = None,
        severity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run full w3goaudit scan on a Solidity file or directory."""
        if not self.is_available():
            raise FileNotFoundError(f"Engine not found at {self.executable}")

        out_path = Path(output_dir) if output_dir else Path(target_path).parent / "w3goaudit_out"
        out_path.mkdir(parents=True, exist_ok=True)

        cmd = [str(self.executable), str(target_path), "-o", str(out_path)]
        if severity:
            cmd.extend(["-s", severity])

        logger.info("Executing w3goaudit scan: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.warning("w3goaudit returned exit code %d: %s", proc.returncode, proc.stderr)

        # Load generated artifacts
        data_dir = out_path / "data"
        findings_file = data_dir / "findings.json"
        auth_file = data_dir / "authorization.json"

        findings = []
        if findings_file.exists():
            with open(findings_file, "r", encoding="utf-8") as f:
                findings_data = json.load(f)
                findings = findings_data.get("findings", [])

        auth_facts = {}
        if auth_file.exists():
            with open(auth_file, "r", encoding="utf-8") as f:
                auth_data = json.load(f)
                auth_facts = {fact["id"]: fact for fact in auth_data.get("facts", [])}

        return {
            "output_dir": str(out_path),
            "findings_count": len(findings),
            "findings": findings,
            "authorization_facts": auth_facts,
            "stdout": proc.stdout,
        }

    def extract_bundle(
        self,
        function_name: str,
        source_path: Path | str,
        contract_name: Optional[str] = None,
        output_format: str = "json",
    ) -> Dict[str, Any] | str:
        """Use 'w3goaudit extract bundle' to get rich AST-based context for LLM."""
        if not self.is_available():
            raise FileNotFoundError(f"Engine not found at {self.executable}")

        cmd = [
            str(self.executable),
            "extract",
            "bundle",
            function_name,
            str(source_path),
            f"--format={output_format}",
        ]
        if contract_name:
            cmd.extend(["--contract", contract_name])

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.warning("extract bundle failed: %s", proc.stderr.strip())
            return {} if output_format == "json" else proc.stderr

        output_str = proc.stdout.strip()
        if output_format == "json":
            try:
                return json.loads(output_str)
            except Exception:
                return {"raw_bundle": output_str}
        return output_str
