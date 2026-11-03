from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ContextBundle:
    """Kết quả Context Assembly cho một finding."""
    # Metadata
    pattern_id: str
    function_name: str
    completeness_score: float  # 0.0 – 1.0: bao nhiêu % signals đã thu thập được
    completeness_notes: List[str] = field(default_factory=list)

    # Context signals
    external_visibility: Optional[bool] = None       # True = external/public, False = internal/private
    has_local_guard: Optional[bool] = None           # require/revert trong thân hàm
    guard_statements: List[str] = field(default_factory=list)  # nội dung các guard
    modifiers_on_function: List[str] = field(default_factory=list)  # modifier của hàm
    modifiers_in_contract: List[str] = field(default_factory=list)  # modifier contract định nghĩa
    inheritance_chain: List[str] = field(default_factory=list)  # is FeeManager, is Ownable...
    external_libraries: List[str] = field(default_factory=list)  # using SafeCast for uint256
    caller_functions: List[str] = field(default_factory=list)   # hàm nào gọi đến hàm bị cảnh báo
    caller_has_guard: Optional[bool] = None         # caller có guard không (nếu biết)
    state_variables_written: List[str] = field(default_factory=list)  # state vars bị ghi
    is_assembly_context: bool = False               # có inline assembly không
    is_unchecked_context: bool = False              # có unchecked block không
    is_initializer: bool = False                    # có initializer modifier không
    is_upgradeable: bool = False                    # kế thừa Upgradeable không
    uses_safecast: bool = False                     # dùng SafeCast library không
    timelock_present: bool = False                  # có timelock modifier không
    timelock_delay_visible: Optional[bool] = None  # delay của timelock có trong snippet không

    # Reentrancy signals (Đợt 3)
    has_reentrancy_guard: bool = False              # nonReentrant modifier or ReentrancyGuard
    has_external_call: bool = False                 # .call, .transfer, .send, etc.
    is_cei_compliant: Optional[bool] = None         # Checks-Effects-Interactions respected
    is_view_or_pure: bool = False                   # view or pure function
    custom_guard_present: bool = False              # custom/conditional modifier present

    # Delegatecall signals (Đợt 4A — SOL-DELEGATECALL-001)
    has_delegatecall: bool = False                  # delegatecall present in code
    delegatecall_target_fixed: Optional[bool] = None   # True=immutable/whitelist, False=param/mutable, None=unknown
    has_implementation_whitelist: bool = False      # approvedImpls or similar mapping gate
    has_upgrade_timelock: bool = False              # timelock before implementation change
    is_diamond_proxy: bool = False                  # EIP-2535 Diamond pattern
    is_uups_proxy: bool = False                     # UUPS / UUPSUpgradeable pattern
    target_from_storage: Optional[bool] = None     # True=from state var, False=from param, None=unknown

    # Arbitrary from signals (Đợt 4A — SOL-ARBITRARY-FROM-001)
    has_transfer_from: bool = False                 # transferFrom call present
    from_is_msg_sender: Optional[bool] = None       # True=from==msg.sender, False=param, None=unknown
    has_signature_verify: bool = False              # EIP-712/ECDSA signature verification before call
    has_permit_pattern: bool = False                # EIP-2612 permit() call present
    from_has_require_check: Optional[bool] = None   # require(from==msg.sender) present

    # Unchecked return signals (Đợt 4A — SOL-UNCHECKED-RETURN-001)
    has_low_level_call: bool = False                # low-level .call() present
    return_value_checked: Optional[bool] = None     # True=require/if-revert on result, False=ignored
    uses_safe_erc20: bool = False                   # SafeERC20 / safeTransfer used
    has_assembly_call: bool = False                 # delegatecall/call in assembly block
    is_fire_and_forget: Optional[bool] = None       # intentional ignore (notification pattern)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_str(self) -> str:
        """Format context bundle thành chuỗi inject vào AI prompt."""
        lines = [
            f"=== CONTEXT ASSEMBLY REPORT ===",
            f"Pattern: {self.pattern_id}",
            f"Function: {self.function_name}",
            f"Completeness: {self.completeness_score:.0%} ({', '.join(self.completeness_notes) if self.completeness_notes else 'No signals missing'})",
            "",
        ]

        if self.external_visibility is not None:
            lines.append(f"Visibility: {'external/public' if self.external_visibility else 'internal/private'}")
        if self.modifiers_on_function:
            lines.append(f"Function Modifiers: {', '.join(self.modifiers_on_function)}")
        if self.has_local_guard is not None:
            lines.append(f"Local Guard: {'YES' if self.has_local_guard else 'NO'}")
        if self.guard_statements:
            for g in self.guard_statements[:3]:
                lines.append(f"  Guard: {g.strip()[:80]}")
        if self.uses_safecast:
            lines.append(f"SafeCast Library: YES (using SafeCast for ...)")
        if self.inheritance_chain:
            lines.append(f"Inherits: {', '.join(self.inheritance_chain)}")
        if self.external_libraries:
            lines.append(f"External Libraries: {', '.join(self.external_libraries)}")
        if self.is_assembly_context:
            lines.append(f"⚠ Contains inline assembly — static analysis limited")
        if self.is_unchecked_context:
            lines.append(f"⚠ Contains unchecked block — Solidity 0.8+ overflow checks disabled")
        if self.is_initializer:
            lines.append(f"Pattern: Proxy initializer (initializer modifier) — one-time call only")
        if self.is_upgradeable:
            lines.append(f"Pattern: Upgradeable proxy — implementation can be replaced")
        if self.timelock_present:
            delay_info = "visible in snippet" if self.timelock_delay_visible else "NOT visible — check deployment config"
            lines.append(f"Timelock: YES (delay {delay_info})")
        if self.caller_functions:
            lines.append(f"Known Callers: {', '.join(self.caller_functions[:5])}")
        if self.caller_has_guard is not None:
            lines.append(f"Caller Has Guard: {'YES' if self.caller_has_guard else 'NO'}")
        if self.state_variables_written:
            lines.append(f"State Written: {', '.join(self.state_variables_written[:5])}")
        if self.has_reentrancy_guard:
            lines.append(f"Reentrancy Guard: YES (nonReentrant / ReentrancyGuard active)")
        if self.has_external_call:
            lines.append(f"External Call: YES (makes external call to untrusted address)")
        if self.is_cei_compliant is not None:
            lines.append(f"CEI Pattern: {'COMPLIANT (State updated before call)' if self.is_cei_compliant else 'VIOLATED (State updated after call — reentrancy risk!)'}")
        if self.is_view_or_pure:
            lines.append(f"Function Type: View/Pure (Potential target for Read-Only Reentrancy)")
        if self.custom_guard_present:
            lines.append(f"⚠ Custom/Conditional Guard: Present but implementation details needed")

        # Delegatecall signals
        if self.has_delegatecall:
            lines.append(f"Delegatecall: YES — code performs delegatecall")
        if self.delegatecall_target_fixed is not None:
            lines.append(f"Delegatecall Target: {'FIXED (immutable/whitelist)' if self.delegatecall_target_fixed else 'MUTABLE/PARAM — attacker may control target address'}")
        if self.has_implementation_whitelist:
            lines.append(f"Implementation Whitelist: YES (approvedImpls mapping or equivalent)")
        if self.has_upgrade_timelock:
            lines.append(f"Upgrade Timelock: YES — implementation changes require time delay")
        if self.is_diamond_proxy:
            lines.append(f"Pattern: EIP-2535 Diamond Proxy — facets governed via diamondCut()")
        if self.is_uups_proxy:
            lines.append(f"Pattern: UUPS Proxy — upgrades require _authorizeUpgrade override")
        if self.target_from_storage is not None:
            lines.append(f"Target Source: {'from state variable (check mutability)' if self.target_from_storage else 'from function parameter (HIGH RISK)'}")

        # Arbitrary from signals
        if self.has_transfer_from:
            lines.append(f"transferFrom: YES — contract calls transferFrom on token")
        if self.from_is_msg_sender is not None:
            lines.append(f"from Address: {'SAFE — hardcoded to msg.sender' if self.from_is_msg_sender else 'PARAM/EXTERNAL — not necessarily msg.sender (RISK)'}")
        if self.has_permit_pattern:
            lines.append(f"EIP-2612 Permit: YES — ECDSA signed authorization before transferFrom")
        if self.has_signature_verify:
            lines.append(f"Signature Verification: YES — ECDSA/EIP-712 verification present")
        if self.from_has_require_check is not None:
            lines.append(f"from Require Guard: {'YES — require(from==msg.sender) enforced' if self.from_has_require_check else 'NO — from not validated against caller'}")

        # Unchecked return signals
        if self.has_low_level_call:
            lines.append(f"Low-level .call(): YES — result must be checked")
        if self.return_value_checked is not None:
            lines.append(f"Return Value Check: {'YES — require/if-revert on success flag' if self.return_value_checked else 'NO — return value ignored (RISK)'}")
        if self.uses_safe_erc20:
            lines.append(f"SafeERC20: YES — OZ safeTransfer/safeTransferFrom wraps return check")
        if self.has_assembly_call:
            lines.append(f"Assembly Call: YES — check assembly for manual success validation")
        if self.is_fire_and_forget is not None:
            lines.append(f"Fire-and-Forget: {'YES — intentional ignore (verify design intent)' if self.is_fire_and_forget else 'NO — failure should be handled'}")

        missing_signals = self._missing_signals()
        if missing_signals:
            lines.append("")
            lines.append(f"MISSING CONTEXT (→ may need Uncertain label):")
            for m in missing_signals:
                lines.append(f"  - {m}")

        return "\n".join(lines)

    def _missing_signals(self) -> List[str]:
        missing = []
        if self.caller_functions == [] and self.external_visibility is False:
            missing.append("Internal function: callers not visible — cannot determine input validation")
        if self.timelock_present and not self.timelock_delay_visible:
            missing.append("Timelock delay not in snippet — check deployment config (delay=0 is unsafe)")
        if self.is_assembly_context:
            missing.append("Inline assembly present — cannot statically determine value bounds")
        if self.is_upgradeable and "Ownable" not in " ".join(self.inheritance_chain):
            missing.append("Upgradeable proxy without visible Ownable — proxy admin may bypass roles")
        if self.custom_guard_present and not self.has_reentrancy_guard:
            missing.append("Custom/conditional modifier present — need full modifier definition to verify reentrancy lock")
        if self.has_external_call and self.is_cei_compliant is None:
            missing.append("External call present — state update order ambiguous without cross-function call graph")
        return missing


# ============================================================================
# Pattern-specific signal extractors
# ============================================================================

def _extract_uint128_signals(code: str, ctx: ContextBundle) -> None:
    """Trích xuất signals cho SOL-UINT128-NARROWING-001."""

    # SafeCast detection
    if re.search(r'using\s+SafeCast\s+for', code):
        ctx.uses_safecast = True
    if re.search(r'\.(toUint128|toUint96|toUint64|toUint32)\s*\(', code):
        ctx.uses_safecast = True

    # Bound check guard
    bound_patterns = [
        r'require\s*\([^;]*(?:type\s*\(\s*uint128\s*\)\s*\.max|2\s*\*\*\s*128)',
        r'require\s*\([^;]*<=\s*type\s*\(\s*uint128\s*\)',
        r'if\s*\([^)]*>\s*type\s*\(\s*uint128\s*\)',
        r'revert\s+(?:Overflow|overflow)',
    ]
    for pat in bound_patterns:
        m = re.search(pat, code, re.IGNORECASE)
        if m:
            ctx.has_local_guard = True
            ctx.guard_statements.append(m.group(0))

    if ctx.has_local_guard is None and re.search(r'uint128\s*\(', code):
        ctx.has_local_guard = False

    # Unchecked block
    if re.search(r'\bunchecked\s*\{', code):
        ctx.is_unchecked_context = True

    # Assembly
    if re.search(r'\bassembly\s*\{', code):
        ctx.is_assembly_context = True

    # State variables written (uint128 type)
    for m in re.finditer(r'uint128\s+(?:public|private|internal)?\s*(\w+)', code):
        ctx.state_variables_written.append(m.group(1))


def _extract_access_control_signals(code: str, ctx: ContextBundle) -> None:
    """Trích xuất signals cho SOL-ACCESS-CONTROL-001."""

    # Standard modifiers
    standard_modifiers = ['onlyOwner', 'onlyRole', 'onlyAdmin', 'onlyGovernance',
                          'onlyOperator', 'onlyManager', 'onlyTimelock', 'onlyMultisig',
                          'onlyGuardian', 'onlyExecutor', 'onlyProposer']
    for mod in standard_modifiers:
        if re.search(rf'\b{mod}\b', code):
            if mod not in ctx.modifiers_on_function:
                ctx.modifiers_on_function.append(mod)
            if mod == 'onlyTimelock':
                ctx.timelock_present = True

    # Custom modifiers in definition (modifier name() ...)
    for m in re.finditer(r'\bmodifier\s+(\w+)\s*\(', code):
        mod_name = m.group(1)
        if mod_name not in ctx.modifiers_in_contract:
            ctx.modifiers_in_contract.append(mod_name)

    # Require-based auth
    auth_patterns = [
        r'require\s*\(\s*msg\.sender\s*==',
        r'require\s*\(\s*hasRole\s*\(',
        r'require\s*\(\s*admins\s*\[',
        r'require\s*\(\s*authorized\s*\[',
        r'require\s*\(\s*isOwner\s*\(',
        r'if\s*\(\s*msg\.sender\s*!=.*revert',
    ]
    for pat in auth_patterns:
        m = re.search(pat, code, re.IGNORECASE)
        if m:
            if ctx.has_local_guard is None:
                ctx.has_local_guard = True
            ctx.guard_statements.append(m.group(0).strip())

    if ctx.has_local_guard is None and ctx.modifiers_on_function:
        ctx.has_local_guard = True

    # Timelock delay visible
    if ctx.timelock_present:
        if re.search(r'(?:minDelay|delay)\s*=\s*\d+', code):
            ctx.timelock_delay_visible = True
            # Check if delay = 0 (dangerous!)
            if re.search(r'(?:minDelay|delay)\s*=\s*0\b', code):
                ctx.guard_statements.append("WARNING: TimelockController delay=0 — provides no protection!")
        else:
            ctx.timelock_delay_visible = False

    # Initializer / upgradeable
    if re.search(r'\binitializer\b', code):
        ctx.is_initializer = True
        ctx.has_local_guard = True  # initializer IS an access control mechanism
    if re.search(r'Upgradeable|UUPS|TransparentUpgradeable', code):
        ctx.is_upgradeable = True

    # AccessControl pattern
    if re.search(r'hasRole\s*\(', code):
        ctx.guard_statements.append("hasRole() check present")

    # Multi-sig
    if re.search(r'(?:multisig|multiSig|MultiSig|GnosisSafe|gnosis)', code, re.IGNORECASE):
        ctx.modifiers_on_function.append("multisig-backed")


def _extract_reentrancy_signals(code: str, ctx: ContextBundle) -> None:
    """Trích xuất signals cho SOL-REENTRANCY-001 (Đợt 3)."""
    # Mutex / guard detection
    if re.search(r'\bnonReentrant\b', code):
        ctx.has_reentrancy_guard = True
        ctx.has_local_guard = True
        if "nonReentrant" not in ctx.modifiers_on_function:
            ctx.modifiers_on_function.append("nonReentrant")

    if re.search(r'ReentrancyGuard', code):
        if "ReentrancyGuard" not in ctx.inheritance_chain:
            ctx.inheritance_chain.append("ReentrancyGuard")
        ctx.has_reentrancy_guard = True

    # Custom or conditional guard detection
    if re.search(r'\bmodifier\s+(\w*(?:guard|lock)\w*)\s*\(', code, re.IGNORECASE) or re.search(r'\b(guarded|conditionalGuard)\b', code):
        ctx.custom_guard_present = True

    # View / pure function check (read-only reentrancy target)
    if re.search(r'\bfunction\s+\w+\s*\([^)]*\)\s*(?:external|public)?[^\n{]*(?:\bview\b|\bpure\b)', code):
        ctx.is_view_or_pure = True

    # External call detection
    ext_call_patterns = [
        r'\.call\s*\{[^}]*value\s*:',
        r'\.call\s*\(',
        r'\.transfer\s*\(',
        r'\.send\s*\(',
        r'IERC20\s*\([^)]*\)\s*\.transfer',
        r'router\s*\.\w+\s*\{',
        r'ICallback\s*\([^)]*\)\s*\.\w+',
    ]
    for pat in ext_call_patterns:
        m = re.search(pat, code)
        if m:
            ctx.has_external_call = True
            break

    # State update and CEI ordering
    state_patterns = [
        r'balances\s*\[[^\]]+\]\s*[-+=]=?',
        r'commitments\s*\[[^\]]+\]\s*[-+=]=?',
        r'shares\s*\[[^\]]+\]\s*[-+=]=?',
        r'reserve\d\s*[-+=]=?',
        r'pendingReward\s*\[[^\]]+\]\s*[-+=]=?',
        r'totalCommitments\s*[-+=]=?',
        r'profits\s*\[[^\]]+\]\s*[-+=]=?',
    ]
    state_pos = -1
    for sp in state_patterns:
        sm = re.search(sp, code)
        if sm:
            ctx.state_variables_written.append(sm.group(0).split('[')[0].strip())
            if state_pos == -1 or sm.start() < state_pos:
                state_pos = sm.start()

    # Find external call position
    call_pos = -1
    for cp in ext_call_patterns:
        cm = re.search(cp, code)
        if cm:
            if call_pos == -1 or cm.start() < call_pos:
                call_pos = cm.start()

    if call_pos != -1 and state_pos != -1:
        ctx.is_cei_compliant = (state_pos < call_pos)


def _extract_delegatecall_signals(code: str, ctx: ContextBundle) -> None:
    """Trích xuất signals cho SOL-DELEGATECALL-001 (Đợt 4A)."""
    if "delegatecall" in code:
        ctx.has_delegatecall = True

    # Check for immutable target
    if re.search(r'immutable\s+\w*impl', code, re.IGNORECASE) or "immutable implementation" in code:
        ctx.delegatecall_target_fixed = True
        ctx.target_from_storage = True

    # Whitelist
    if re.search(r'(approvedImpls|whitelist|trustedModules)\s*\[', code, re.IGNORECASE):
        ctx.has_implementation_whitelist = True

    # Timelock / delay
    if re.search(r'(UPGRADE_DELAY|upgradeTimestamp|timelockController|assertProposed)', code, re.IGNORECASE):
        ctx.has_upgrade_timelock = True

    # Diamond proxy standard
    if "Diamond" in code or "diamondCut" in code or "LibDiamond" in code:
        ctx.is_diamond_proxy = True
        ctx.delegatecall_target_fixed = True

    # UUPS proxy
    if "UUPS" in code or "_authorizeUpgrade" in code:
        ctx.is_uups_proxy = True

    # Check if target is parameter
    if re.search(r'function\s+\w+\s*\([^)]*address\s+(_target|module|target|impl|newImpl)[^)]*\)', code):
        if ctx.delegatecall_target_fixed is None:
            ctx.delegatecall_target_fixed = False
        ctx.target_from_storage = False

    # Check if target is state variable
    if re.search(r'address\s+(?:public|private|internal)\s+(impl|currentImpl|implementation)', code):
        ctx.target_from_storage = True


def _extract_arbitrary_from_signals(code: str, ctx: ContextBundle) -> None:
    """Trích xuất signals cho SOL-ARBITRARY-FROM-001 (Đợt 4A)."""
    if "transferFrom" in code:
        ctx.has_transfer_from = True

    # Check if from is msg.sender
    if re.search(r'transferFrom\s*\(\s*msg\.sender\s*,', code):
        ctx.from_is_msg_sender = True
        ctx.from_has_require_check = True

    # Check explicit require(from == msg.sender)
    if re.search(r'require\s*\(\s*from\s*==\s*msg\.sender', code):
        ctx.from_has_require_check = True
        ctx.from_is_msg_sender = True

    # Check EIP-2612 permit
    if "permit(" in code:
        ctx.has_permit_pattern = True

    # Check signature verification
    if "ECDSA" in code or "recover(" in code or "verify(" in code:
        ctx.has_signature_verify = True

    # Check if from is parameter without guard
    if re.search(r'function\s+\w+\s*\([^)]*address\s+from[^)]*\)', code):
        if ctx.from_is_msg_sender is None:
            ctx.from_is_msg_sender = False


def _extract_unchecked_return_signals(code: str, ctx: ContextBundle) -> None:
    """Trích xuất signals cho SOL-UNCHECKED-RETURN-001 (Đợt 4A)."""
    if ".call{" in code or ".call(" in code:
        ctx.has_low_level_call = True

    # Check SafeERC20
    if "SafeERC20" in code or "safeTransfer" in code:
        ctx.uses_safe_erc20 = True
        ctx.return_value_checked = True

    # Check return capture and check
    if re.search(r'\(\s*bool\s+(?:success|ok)\b[^)]*\)\s*=\s*[^;]*\.call', code):
        if re.search(r'require\s*\(\s*(?:success|ok)\b', code) or re.search(r'if\s*\(\s*!(?:success|ok)\b', code):
            ctx.return_value_checked = True
        elif "revert(" in code and ("iszero" in code or "success" in code):
            ctx.return_value_checked = True
        else:
            # Captured but not checked to revert (e.g. only logged in event)
            ctx.return_value_checked = False
    elif ctx.has_low_level_call and not ctx.uses_safe_erc20:
        # call called without capturing return
        if re.search(r'\w+\.call\{[^}]*\}\s*\([^)]*\)\s*;', code) or re.search(r'\w+\.call\([^)]*\)\s*;', code):
            ctx.return_value_checked = False

    # Check assembly call
    if "assembly" in code and "call(" in code:
        ctx.has_assembly_call = True
        if "iszero(success)" in code and "revert(" in code:
            ctx.return_value_checked = True

    # Check intentional fire-and-forget
    if "fire-and-forget" in code.lower() or "deliberately not checking" in code.lower():
        ctx.is_fire_and_forget = True


# ============================================================================
# Main Assembly Function
# ============================================================================

def assemble_context_from_snippet(
    code_snippet: str,
    pattern_id: str,
    function_name: str = "unknown",
    full_source: Optional[str] = None,
) -> ContextBundle:
    """
    Trích xuất context bundle từ code snippet (và full source nếu có).

    Args:
        code_snippet: Đoạn code từ finding (hàm bị cảnh báo)
        pattern_id: Pattern ID (SOL-UINT128-NARROWING-001 hoặc SOL-ACCESS-CONTROL-001)
        function_name: Tên hàm bị cảnh báo (optional)
        full_source: Toàn bộ source file nếu có (để tìm callers)

    Returns:
        ContextBundle chứa tất cả signals đã thu thập
    """
    source_to_analyze = full_source or code_snippet
    ctx = ContextBundle(pattern_id=pattern_id, function_name=function_name, completeness_score=0.0)

    # --- Visibility detection ---
    func_match = re.search(
        r'function\s+\w+\s*\([^)]*\)\s*(external|public|internal|private)',
        source_to_analyze
    )
    if func_match:
        vis = func_match.group(1)
        ctx.external_visibility = vis in ('external', 'public')

    # --- Inheritance chain ---
    for m in re.finditer(r'\bcontract\s+\w+\s+is\s+([\w,\s]+)\{', source_to_analyze):
        parents = [p.strip() for p in m.group(1).split(',')]
        ctx.inheritance_chain.extend(parents)

    # --- External libraries ---
    for m in re.finditer(r'using\s+([\w\.]+)\s+for', source_to_analyze):
        lib = m.group(1)
        if lib not in ctx.external_libraries:
            ctx.external_libraries.append(lib)

    # --- Caller detection (needs full source) ---
    if full_source and function_name != "unknown":
        for m in re.finditer(r'function\s+(\w+)', full_source):
            fname = m.group(1)
            if fname != function_name:
                # Check if this function calls our target
                start = m.start()
                next_func = full_source.find('\nfunction ', start + 1)
                body = full_source[start:next_func] if next_func > 0 else full_source[start:]
                if function_name + '(' in body and fname not in ctx.caller_functions:
                    ctx.caller_functions.append(fname)

    # --- Extract modifiers and pattern signals ---
    _extract_access_control_signals(source_to_analyze, ctx)
    if 'UINT128' in pattern_id:
        _extract_uint128_signals(source_to_analyze, ctx)
    if 'REENTRANCY' in pattern_id:
        _extract_reentrancy_signals(source_to_analyze, ctx)
    if 'DELEGATECALL' in pattern_id:
        _extract_delegatecall_signals(source_to_analyze, ctx)
    if 'ARBITRARY-FROM' in pattern_id or 'ARBITRARY_FROM' in pattern_id:
        _extract_arbitrary_from_signals(source_to_analyze, ctx)
    if 'UNCHECKED-RETURN' in pattern_id or 'UNCHECKED_RETURN' in pattern_id:
        _extract_unchecked_return_signals(source_to_analyze, ctx)

    # --- Completeness scoring ---
    signals_present = 0
    signals_total = 5  # visibility, guard, modifier, inheritance, library

    if ctx.external_visibility is not None:
        signals_present += 1
    if ctx.has_local_guard is not None:
        signals_present += 1
    if ctx.modifiers_on_function or ctx.modifiers_in_contract:
        signals_present += 1
    if ctx.inheritance_chain:
        signals_present += 1
    if ctx.external_libraries or ctx.uses_safecast:
        signals_present += 1

    ctx.completeness_score = signals_present / signals_total

    # --- Completeness notes ---
    if ctx.caller_functions == [] and ctx.external_visibility is False:
        ctx.completeness_notes.append("No callers visible for internal function")
    if ctx.is_assembly_context:
        ctx.completeness_notes.append("Assembly block limits static analysis")
    if ctx.timelock_present and not ctx.timelock_delay_visible:
        ctx.completeness_notes.append("Timelock delay not visible in snippet")
    if not ctx.completeness_notes:
        ctx.completeness_notes.append("Sufficient context available")

    return ctx


def assemble_context_for_case(case: dict, full_source: Optional[str] = None) -> ContextBundle:
    """Wrapper để dùng với pilot dataset case dict."""
    func_match = re.search(
        r'function\s+(\w+)\s*\(',
        case.get('code_snippet', '')
    )
    func_name = func_match.group(1) if func_match else case.get('case_id', 'unknown')
    return assemble_context_from_snippet(
        code_snippet=case.get('code_snippet', ''),
        pattern_id=case.get('pattern_id', 'UNKNOWN'),
        function_name=func_name,
        full_source=full_source,
    )
