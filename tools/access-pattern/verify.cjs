// Synthetic local tests only; reuse the pinned compiler/EVM dependencies of the first pilot.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const requireRuntime = createRequire(path.resolve(__dirname, '../cast-pattern/package.json'));
const solc = requireRuntime('solc');
const ganache = requireRuntime('ganache');
const { BrowserProvider, ContractFactory, getAddress } = requireRuntime('ethers');
const root = path.resolve(__dirname, '../..');
const fixture = path.join(root, 'tests/fixtures/patterns/missing-access-control');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');

async function main() {
  const names = ['UnsafeFeeConfig.sol', 'GuardedFeeConfig.sol', 'UnknownFragment.sol'];
  const inputs = Object.fromEntries(names.map(n => [n, fs.readFileSync(path.join(fixture, n), 'utf8')]));
  const fragment = inputs['UnknownFragment.sol'];
  function wrapper(name, guard) {
    return `contract ${name} {
      address public immutable owner;
      address public feeRecipient;
      constructor() { owner = msg.sender; feeRecipient = msg.sender; }
      function setFeeRecipient(address recipient) external {
        ${guard ? 'require(msg.sender == owner, "unauthorized");' : ''}
        _setFeeRecipient(recipient);
      }
      ${fragment}
    }`;
  }
  const harness = '// SPDX-License-Identifier: MIT\npragma solidity 0.8.24;\n' +
    wrapper('GuardedCaller', true) + '\n' + wrapper('UnguardedCaller', false);
  const sources = {
    'UnsafeFeeConfig.sol': {content: inputs['UnsafeFeeConfig.sol']},
    'GuardedFeeConfig.sol': {content: inputs['GuardedFeeConfig.sol']},
    'ContextHarness.sol': {content: harness},
  };
  const settings = {optimizer:{enabled:false}, evmVersion:'shanghai', outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}};
  const compiled = JSON.parse(solc.compile(JSON.stringify({language:'Solidity', sources, settings})));
  assert.deepEqual((compiled.errors || []).filter(e => e.severity === 'error'), []);
  const rpc = ganache.provider({logging:{quiet:true}, wallet:{totalAccounts:3, seed:'public-local-access-pattern-fixture'}, chain:{hardfork:'shanghai'}});
  const provider = new BrowserProvider(rpc);
  provider.pollingInterval = 10;
  try {
    const signers = await Promise.all([0,1,2].map(i => provider.getSigner(i)));
    const roles = ['owner','outsiderA','outsiderB'];
    const accounts = Object.fromEntries(await Promise.all(signers.map(async (s,i) => [roles[i],await s.getAddress()])));
    const scenarios = [[1,1],[0,2],[2,1],[0,0],[1,2],[0,1]];
    const executions = [];
    for (const [file,name,guarded] of [
      ['UnsafeFeeConfig.sol','UnsafeFeeConfig',false],
      ['GuardedFeeConfig.sol','GuardedFeeConfig',true],
      ['ContextHarness.sol','GuardedCaller',true],
      ['ContextHarness.sol','UnguardedCaller',false],
    ]) {
      const artifact = compiled.contracts[file][name];
      const contract = await new ContractFactory(artifact.abi,artifact.evm.bytecode.object,signers[0]).deploy();
      await contract.waitForDeployment();
      assert.equal(await contract.owner(), accounts.owner);
      assert.equal(await contract.feeRecipient(), accounts.owner);
      const observations = [];
      for (const [callerIndex,recipientIndex] of scenarios) {
        const callerRole = roles[callerIndex];
        const recipient = accounts[roles[recipientIndex]];
        assert.notEqual(BigInt(recipient),0n);
        const before = await contract.feeRecipient();
        assert.notEqual(before,recipient,'use a real state change to expose missing authorization');
        const connected = contract.connect(signers[callerIndex]);
        const shouldReject = guarded && callerIndex !== 0;
        let reason = null;
        if (shouldReject) {
          // Ensure the failure is authorization, not invalid input or another accidental revert.
          try { await connected.setFeeRecipient.staticCall(recipient); }
          catch (error) { assert.equal(error.code,'CALL_EXCEPTION'); reason = error.reason; }
          assert.equal(reason,'unauthorized');
        }
        let receipt;
        let reverted = false;
        try { receipt = await (await connected.setFeeRecipient(recipient,{gasLimit:150000})).wait(); }
        catch (error) {
          if (error.code !== 'CALL_EXCEPTION' || !error.receipt || error.receipt.status !== 0) throw error;
          receipt = error.receipt;
          reverted = true;
        }
        const after = await contract.feeRecipient();
        assert.equal(reverted,shouldReject);
        assert.equal(after,shouldReject ? before : getAddress(recipient));
        assert.equal(await contract.owner(),accounts.owner);
        observations.push({caller_role:callerRole,caller:accounts[callerRole],recipient,before,after,
          reverted,transaction_status:receipt.status,revert_reason:reason,
          unauthorized_change:callerIndex !== 0 && !reverted && before !== after});
      }
      executions.push({contract:name,bytecode_sha256:sha(artifact.evm.bytecode.object),observations});
    }
    const report = {
      schema_version:'1.0',pattern_id:'SOL-MISSING-ACCESS-CONTROL-001',
      compiler:solc.version(),runtime:'ganache@7.9.2',settings,
      synthetic:true,public_network_used:false,accounts,
      fixture_hashes:Object.fromEntries(names.map(n=>[n,sha(inputs[n])])),
      runner_sha256:sha(fs.readFileSync(__filename)),
      dependency_lock_sha256:sha(fs.readFileSync(path.join(root,'tools/cast-pattern/pnpm-lock.yaml'))),
      generated_context_harness:harness,executions,
      checks:executions.reduce((n,e)=>n+e.observations.length,0),
      expected_labels:{unsafe:'confirmed',guarded:'false_positive_for_this_pattern',fragment:'insufficient_context'},
      limitations:['Synthetic feeRecipient example, not a reproduction of the Sherlock pool-activation finding.',
        'Confirms unauthorized configuration writes only; no fee transfer, monetary loss or severity tested.',
        'Guarded verdict covers this pattern and entry path only; wrappers are hypothetical callers.'],
    };
    const output = path.join(root,'data/processed/access-pattern-validation.json');
    fs.writeFileSync(output+'.tmp',JSON.stringify(report,null,2)+'\n');
    fs.renameSync(output+'.tmp',output);
    console.log(JSON.stringify({output,checks:report.checks,labels:report.expected_labels}));
  } finally { await provider.destroy(); await rpc.disconnect(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
