// Isolated synthetic contracts only. In-process EVM; no HTTP listener or public RPC.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const solc = require('solc');
const ganache = require('ganache');
const { BrowserProvider, ContractFactory } = require('ethers');
const root = path.resolve(__dirname, '../..');
const fixture = path.join(root, 'tests/fixtures/patterns/uint128-narrowing');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');

async function main() {
  const names = ['UnsafeReserve.sol', 'GuardedReserve.sol', 'UnknownFragment.sol'];
  const inputs = Object.fromEntries(names.map(name => [name, fs.readFileSync(path.join(fixture, name), 'utf8')]));
  const fragment = inputs['UnknownFragment.sol'];
  // Two explicit hypothetical completions of the SAME fragment. Neither is
  // asserted to be the missing original caller of a real finding.
  const wrappers = `// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;
contract GuardedCaller {
  uint128 public reserve;
  function record(uint256 amount) external {
    require(amount <= type(uint128).max, "amount exceeds uint128");
    _record(amount);
  }
  ${fragment}
}
contract UnguardedCaller {
  uint128 public reserve;
  function record(uint256 amount) external { _record(amount); }
  ${fragment}
}`;
  const sources = {
    'UnsafeReserve.sol': {content: inputs['UnsafeReserve.sol']},
    'GuardedReserve.sol': {content: inputs['GuardedReserve.sol']},
    'ContextHarness.sol': {content: wrappers},
  };
  const settings = {optimizer: {enabled:false}, evmVersion:'shanghai', outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}};
  const compiled = JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources,settings})));
  const errors = (compiled.errors || []).filter(e => e.severity === 'error');
  assert.equal(errors.length, 0, JSON.stringify(errors));
  const rpc = ganache.provider({logging:{quiet:true},wallet:{totalAccounts:1},chain:{hardfork:'shanghai'}});
  const provider = new BrowserProvider(rpc);
  provider.pollingInterval = 10;
  try {
    const signer = await provider.getSigner();
    const max = (1n << 128n) - 1n;
    const values = [0n, 1n, max-1n, max, max+1n, max+2n, (1n<<256n)-1n];
    // Repeatable extra values test both sides of the bound (not a proof by sampling).
    for(let i=0;i<16;i++) {
      const x = BigInt('0x'+sha('cast-pattern-v1:'+i));
      values.push(x & max, x);
    }
    const executions = [];
    for (const [file,name,guarded] of [
      ['UnsafeReserve.sol','UnsafeReserve',false],
      ['GuardedReserve.sol','GuardedReserve',true],
      ['ContextHarness.sol','GuardedCaller',true],
      ['ContextHarness.sol','UnguardedCaller',false],
    ]) {
      const artifact = compiled.contracts[file][name];
      const contract = await new ContractFactory(artifact.abi,artifact.evm.bytecode.object,signer).deploy();
      await contract.waitForDeployment();
      const observations = [];
      for(const amount of values) {
        const before = await contract.reserve();
        let receipt;
        let rejected = false;
        try {
          receipt = await (await contract.record(amount,{gasLimit:150000})).wait();
        } catch(error) {
          // A transport/compiler error must not count as a successful rejection.
          if(error.code !== 'CALL_EXCEPTION' || !error.receipt || error.receipt.status !== 0) throw error;
          rejected = true;
          receipt = error.receipt;
        }
        const after = await contract.reserve();
        if(guarded && amount > max) {
          assert.equal(rejected,true);
          assert.equal(after,before,'revert must preserve state');
        } else {
          assert.equal(rejected,false);
          assert.equal(after,amount & max);
        }
        observations.push({input:amount.toString(),before:before.toString(),after:after.toString(),
          reverted:rejected,transaction_status:receipt.status,exact_value_preserved:!rejected && after===amount});
      }
      executions.push({contract:name,bytecode_sha256:sha(artifact.evm.bytecode.object),observations});
    }
    const report = {
      pattern_id:'SOL-UINT128-NARROWING-001', schema_version:'1.0',
      compiler:solc.version(), runtime:'ganache@7.9.2', node:process.version,
      settings, synthetic:true, public_network_used:false,
      fixture_hashes:Object.fromEntries(names.map(name=>[name,sha(inputs[name])])),
      generated_context_harness:wrappers, executions,
      checks:executions.reduce((sum,e)=>sum+e.observations.length,0),
      expected_labels:{unsafe:'confirmed',guarded:'false_positive_for_this_pattern',fragment:'insufficient_context'},
      limitations:['Labels concern exact-value-preserving narrowing only, not whole-contract security.',
        'Synthetic examples do not reproduce the Caviar PoC or establish its financial severity.',
        'Finite executions accompany a local range argument; missing-fragment context is not inferred from wrappers.'],
    };
    const output = path.join(root,'data/processed/uint128-pattern-validation.json');
    fs.mkdirSync(path.dirname(output),{recursive:true});
    fs.writeFileSync(output+'.tmp',JSON.stringify(report,null,2)+'\n');
    fs.renameSync(output+'.tmp',output);
    console.log(JSON.stringify({output,checks:report.checks,labels:report.expected_labels,compiler:report.compiler}));
  } finally {
    await provider.destroy();
    await rpc.disconnect();
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
