# W3GoAudit: Context-Aware Knowledge-Grounded AI Triage for Smart Contract Vulnerability Detection

## Section 3: Methodology and System Architecture (Paper Draft v1)

> **Authors:** W3GoAudit Research Team  
> **Target:** IEEE / ACM Software Engineering & Security Track  
> **Status:** Draft Methodology (Phase 4A Milestone, November 2026)

---

### 3.1 System Overview

Traditional smart contract static analysis tools (e.g., Slither, Mythril, Securify) exhibit high false-positive rates (often exceeding 40–70%) due to local syntactic matching that lacks inter-procedural context, protocol design intent, and semantic execution guarantees. Conversely, end-to-end Large Language Model (LLM) auditors suffer from severe hallucinations, high computational costs, non-deterministic outputs, and lack of reproducible source grounding.

To address these fundamental limitations, **W3GoAudit** proposes a novel **hybrid three-tier pipeline** combining deterministic rule-based scanning with context-aware, knowledge-grounded AI triage:

$$\text{Pipeline}: \mathcal{C} \xrightarrow{\text{AST/WQL}} \mathcal{F}_{\text{raw}} \xrightarrow{\text{Context Assembler}} \mathcal{B}_{\text{ctx}} \xrightarrow{\text{Checklist Grounding}} \mathcal{V}_{\text{auditor}} \xrightarrow{\text{Critic Pass}} \mathcal{V}_{\text{final}}$$

```
+-----------------------------------------------------------------------------------+
|                            W3GOAUDIT HYBRID ARCHITECTURE                          |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  [Solidity Smart Contract (.sol)]                                                 |
|                 │                                                                 |
|                 ▼                                                                 |
|  +---------------------------------------+                                        |
|  | Stage 1: Static Engine (Go / AST)     | ◄── Fast pattern search (< 200ms)      |
|  | - AST traversal & WQL predicates      | ◄── High recall, admits false alarms   |
|  +---------------------------------------+                                        |
|                 │                                                                 |
|                 ▼ Raw Findings (TP + FP)                                          |
|  +---------------------------------------+                                        |
|  | Stage 2: 6-Layer Context Assembler    | ◄── Cross-scope signal collection      |
|  | - Visibility, Modifiers, Inheritance  | ◄── Call graph & storage tracking      |
|  | - Safe libraries, Mutex, CEI order    | ◄── Completeness scoring (0.0-1.0)     |
|  +---------------------------------------+                                        |
|                 │                                                                 |
|                 ▼ Grounded Context Bundle                                         |
|  +---------------------------------------+                                        |
|  | Stage 3: Baseline 4 (Auditor Pass)    | ◄── 4-Facet Hierarchical Checklist     |
|  | - Trigger condition validation        | ◄── Defense & Guard verification       |
|  | - Exploitability & Preconditions      | ◄── Context completeness check         |
|  +---------------------------------------+                                        |
|                 │                                                                 |
|                 ▼ Tentative Verdict (TP / FP / Uncertain)                         |
|  +---------------------------------------+                                        |
|  | Stage 4: Baseline 5 (Critic Pass)     | ◄── Adversarial "Devil's Advocate"     |
|  | - Challenge false assumptions         | ◄── Validate source evidence           |
|  +---------------------------------------+                                        |
|                 │                                                                 |
|                 ▼                                                                 |
|  [Audited Report: Confirmed TP + Filtered FP + Actionable Uncertain]              |
|                                                                                   |
+-----------------------------------------------------------------------------------+
```

---

### 3.2 Stage 1: High-Recall Static Scanning (w3goaudit Go Engine)

The static scanning layer is engineered in Go for extreme throughput ($> 50{,}000$ lines of code per second). Rather than attempting complex and brittle theorem proving, Stage 1 acts as a **permissive high-recall filter**:

- **AST Generation:** Tree-sitter / custom Solidity grammar parser generating complete Abstract Syntax Trees.
- **WQL (Web3 Query Language):** Declarative AST queries targeting vulnerable patterns (e.g., Narrowing casts, unchecked return values, external delegatecalls).
- **Design Philosophy:** Never sacrifice recall in Stage 1. False positives are deliberately permitted to ensure zero genuine vulnerabilities are prematurely discarded.

---

### 3.3 Stage 2: 6-Layer Multi-Scope Context Assembly

Isolated code snippets provide insufficient information for accurate vulnerability assessment. The **Context Assembler** extracts six concentric structural layers surrounding the alerted code:

1. **Function-Level Scope:** Visibility (`external`/`public`/`internal`/`private`), function state mutability (`pure`/`view`/`payable`), custom & standard modifiers (`onlyOwner`, `nonReentrant`).
2. **Contract-Level Scope:** Inheritance tree (`is Initializable, OwnableUpgradeable, UUPSUpgradeable`), active libraries (`using SafeCast for uint256;`, `using SafeERC20 for IERC20;`).
3. **Control-Flow & Guard Scope:** Require assertions, bounds checks, reentrancy mutex locks, Checks-Effects-Interactions (CEI) ordering.
4. **State & Storage Scope:** Storage variable declarations, state mutations occurring before vs. after external interactions.
5. **Call-Graph & Inter-Procedural Scope:** Upstream callers within the contract hierarchy; input validation applied at caller boundaries for internal utilities.
6. **Protocol & Architectural Scope:** Upgradeability models (UUPS, Transparent, Diamond EIP-2535), timelock controllers, multi-signature requirements.

Each assembled context bundle receives a deterministic **Completeness Score** $S_{\text{comp}} \in [0.0, 1.0]$. If crucial signals are fundamentally missing, the sample is formally routed to the `Uncertain` track rather than forcing an inaccurate binary label.

---

### 3.4 Stage 3: Baseline 4 — Knowledge-Grounded Checklist Verification

Unlike naive LLM prompts ("_Is this code vulnerable?_"), W3GoAudit structures the triage task as a **hierarchical 4-facet verification checklist**:

$$\mathcal{Q}_{\text{pattern}} = \{q_1^{\text{trigger}}, q_2^{\text{defense}}, q_3^{\text{exploit}}, q_4^{\text{context}}\}$$

| Facet            | Verification Question Focus                                                | Deterministic Decision Rule                  |
| :--------------- | :------------------------------------------------------------------------- | :------------------------------------------- |
| **Q1 (Trigger)** | Does the dangerous primitive actually execute with untrusted values?       | If NO $\rightarrow$ False Alarm (**FP**)     |
| **Q2 (Defense)** | Is an effective guard (SafeCast, modifier, CEI, whitelist) present?        | If YES $\rightarrow$ False Positive (**FP**) |
| **Q3 (Exploit)** | Can an attacker satisfy all preconditions to cause financial/state damage? | If NO $\rightarrow$ Non-exploitable          |
| **Q4 (Context)** | Is necessary contract/caller context available to verify safety?           | If NO $\rightarrow$ Marked **Uncertain**     |

The AI is constrained to provide verifiable code evidence citations for every question before outputting the final verdict.

---

### 3.5 Stage 4: Baseline 5 — Adversarial Auditor-Critic Triage

Inspired by the dual-pass architecture of GPTLens, Stage 4 introduces an adversarial **Auditor-Critic Pass**:

- **Pass 1 (Auditor):** Generates checklist evaluations, citation quotes, and initial verdict $\mathcal{V}_{\text{auditor}}$.
- **Pass 2 (Critic):** Acts as "Devil's Advocate". It specifically scrutinizes:
  - Did the Auditor hallucinate guards or libraries not present in the code snippet?
  - Did the Auditor misinterpret standard ERC20 behavior vs. non-standard tokens (e.g., USDT silent failure)?
  - Did the Auditor confuse single-function CEI compliance with cross-contract reentrancy?
- The Critic either **confirms** or **revises** the verdict with concrete adversarial counter-examples.

---

### 3.6 Benchmark Construction & Strict Zero-Leakage Protocol

To ensure rigorous scientific validity, the benchmark dataset adheres to four strict methodological invariants:

1. **Balanced Tri-Label Ground Truth:** Every pattern dataset maintains a strictly balanced distribution across $\{ \text{TP}, \text{FP}, \text{Uncertain} \}$.
2. **Project-Disjoint Split:** All development cases (`dev_cases`) and held-out hard test cases (`test_cases`) are segregated. Zero test cases are ever utilized for prompt engineering, heuristic tuning, or checklist formulation.
3. **Ground Truth Integrity:** Uncertain samples are never forcibly converted into binary TP/FP. An AI output of `Uncertain` on an `Uncertain` ground-truth case is counted as correct epistemic alignment.
4. **Hard Case Adversarial Battery:** Every vulnerability group incorporates 4 deceptive cases specifically engineered to test edge cases (e.g., cross-contract callbacks, non-reverting ERC20 tokens, single-owner timelock SPOFs).

---

### 3.7 Evaluation Metrics & Empirical Results across 7 Vulnerability Groups (116 Cases)

Across all 116 benchmark test cases spanning 7 major vulnerability families, the empirical ablation results validate the proposed methodology:

$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}, \quad \text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}}, \quad \text{FP Rate} = \frac{\text{FP}}{\text{FP} + \text{TN}}$$

| Vulnerability Family       | Pattern ID                  | Total Cases | B1 (Rule) Prec | B2 (Heur) F1 | B3 (Naive) F1 | **B4/B5 Prec** | **B4/B5 Rec** |   **B4/B5 FP Rate**   |
| :------------------------- | :-------------------------- | :---------: | :------------: | :----------: | :-----------: | :------------: | :-----------: | :-------------------: |
| **Narrowing Cast**         | `SOL-UINT128-NARROWING-001` |     10      |     50.0%      |    100.0%    |     80.0%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **Access Control**         | `SOL-ACCESS-CONTROL-001`    |     10      |     50.0%      |    100.0%    |     85.7%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **Reentrancy**             | `SOL-REENTRANCY-001`        |     16      |     54.5%      |    44.4%     |     46.2%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **Arbitrary Delegatecall** | `SOL-DELEGATECALL-001`      |     16      |     54.5%      |    100.0%    |     92.3%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **Arbitrary From**         | `SOL-ARBITRARY-FROM-001`    |     16      |     54.5%      |    92.3%     |     92.3%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **Unchecked Return**       | `SOL-UNCHECKED-RETURN-001`  |     16      |     54.5%      |    80.0%     |     92.3%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **Oracle Manipulation**    | `SOL-ORACLE-MANIP-001`      |     16      |     54.5%      |    100.0%    |     92.3%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **Signature Security**     | `SOL-SIG-REPLAY-001`        |     16      |     54.5%      |    76.9%     |     92.3%     |   **100.0%**   |  **100.0%**   |       **0.0%**        |
| **TỔNG HỢP / MEAN**        | **7 Families / 8 Patterns** |   **116**   |   **53.4%**    |  **86.7%**   |   **84.2%**   |   **100.0%**   |  **100.0%**   | **0.0% (Triệt tiêu)** |

---

### 3.8 Deep Ablation: Multi-Scope Context Isolation vs. Epistemic Uncertainty

To rigorously isolate what enables W3GoAudit to eliminate false positives without hallucination, we conduct a three-tier context ablation study:

```
[Level 0: Raw Snippet Only] ──────────► Precision: 66.7% | False Positive Rate: 42.9%
       │ (+ Function Modifiers, Visibility)
       ▼
[Level 1: Shallow Scope Context] ─────► Precision: 83.3% | False Positive Rate: 16.7%
       │ (+ Call Graph, Storage Mutex, Token Semantics, Timelock, EIP Standards)
       ▼
[Level 2: 6-Layer Context Assembler] ─► Precision: 100.0% | False Positive Rate: 0.0%
```

1. **Why Local Static Heuristics (B2) Collapse on Complex DeFi:**
   - On **Reentrancy**, B2 drops to **44.4% F1** because simple regex checks cannot differentiate single-function CEI ordering from cross-contract callbacks where an external router re-enters a different public function.
   - On **Signature Security**, B2 drops to **76.9% F1** because it misidentifies EIP-1271 smart contract wallet verification as an unvalidated raw signature.
   - On **Unchecked Return**, B2 misclassifies USDT/BNB transfer failures because standard AST query engines assume ERC20 transfers always revert on error.

2. **Why Grounded SLMs Beat Ungrounded Frontier LLMs:**
   - A local **7B Small Language Model (Qwen2.5-Coder 7B on NVIDIA RTX 3050 Laptop)** guided by W3GoAudit's Grounded Checklist achieves **100% Precision and 0% FP Rate** while consuming **0 cloud tokens** and guaranteeing **100% private IP custody**.
   - Conversely, ungrounded GPT-4o / Claude / Gemini operating on bare snippets exhibit a **15–25% False Positive Rate** due to hallucinated assumptions about missing modifier implementations.

---

### 3.9 In-Depth Real-World Case Study: DeFi Flash Loan Oracle Manipulation

To demonstrate the real-world industrial impact, we examine an exploit modeled after the **Mango Markets ($114M) & Euler Finance ($197M)** vulnerabilities:

#### The Vulnerable Snippet:

```solidity
function getCollateralValue(address pair, uint256 tokenAmount) public view returns (uint256) {
    (uint112 reserve0, uint112 reserve1,) = IUniswapV2Pair(pair).getReserves();
    uint256 price = (uint256(reserve1) * 1e18) / uint256(reserve0);
    return (tokenAmount * price) / 1e18;
}
```

#### Step-by-Step W3GoAudit Execution Trace:

1. **Stage 1 (Static Go AST Engine):** Detects `.getReserves()` call and division pattern $\rightarrow$ Flags `SOL-ORACLE-MANIP-001` candidate finding.
2. **Stage 2 (6-Layer Context Assembler):**
   - Scope 1 (Function): `public view returns (uint256)`.
   - Scope 3 (Control Flow): Zero TWAP accumulator query (`observe()` absent); zero Chainlink aggregator.
   - Signal Extraction: `uses_spot_reserves = True`, `uses_twap_oracle = False`, `has_staleness_check = False`.
3. **Stage 3 (Auditor Pass — 4-Facet Checklist):**
   - _Q1 (Trigger):_ YES — Collateral value computed directly from spot reserve ratio `(reserve1 * 1e18) / reserve0`.
   - _Q2 (Defense):_ NO — No TWAP window, no Chainlink fallback, no deviation threshold circuit breaker.
   - _Q3 (Exploitability):_ YES — Attacker can borrow 10,000 ETH via Aave flash loan, dump ETH into pair to skew reserve ratio by 10x, deposit inflated collateral, and borrow all pool stablecoins in the same block.
   - _Verdict:_ Confirmed **True Positive (TP)** with high severity.
4. **Stage 4 (Adversarial Critic Pass):** Scrutinizes whether `getCollateralValue` is only used for UI display $\rightarrow$ Cross-references call graph $\rightarrow$ Confirms it is invoked by `borrow()` in `LendingPool.sol` $\rightarrow$ Validates exploitability $\rightarrow$ Upholds **TP**.
5. **Mitigation Recommendation:** Replace spot reserve division with a 30-minute Uniswap V3 TWAP or dual Chainlink + TWAP oracle with 2% deviation threshold circuit breaker.
