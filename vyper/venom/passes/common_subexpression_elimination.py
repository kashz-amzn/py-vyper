from vyper.venom.analysis.available_expression import CSEAnalysis
from vyper.venom.analysis.dfg import DFGAnalysis
from vyper.venom.analysis.liveness import LivenessAnalysis
from vyper.venom.basicblock import IRInstruction, IRVariable
from vyper.venom.passes.base_pass import IRPass

# instruction that are not usefull to be
# substituted
UNINTERESTING_OPCODES = frozenset(
    [
        "store",
        "param",
        "offset",
        "phi",
        "nop",
        "calldatasize",
        "returndatasize",
        "gas",
        "gaslimit",
        "gasprice",
        "gaslimit",
        "address",
        "origin",
        "codesize",
        "caller",
        "callvalue",
        "coinbase",
        "timestamp",
        "number",
        "prevrandao",
        "chainid",
        "basefee",
        "blobbasefee",
        "pc",
        "msize",
    ]
)
# intruction that cannot be substituted (without further analysis)
NONIDEMPOTENT_INSTRUCTIONS = frozenset(["log", "call", "staticcall", "delegatecall", "invoke"])


class CSE(IRPass):
    expression_analysis: CSEAnalysis

    def run_pass(self):
        available_expression_analysis = self.analyses_cache.request_analysis(CSEAnalysis)
        assert isinstance(available_expression_analysis, CSEAnalysis)
        self.expression_analysis = available_expression_analysis

        while True:
            replace_dict = self._find_replaceble()
            if len(replace_dict) == 0:
                return

            self._replace(replace_dict)
            self.analyses_cache.invalidate_analysis(DFGAnalysis)
            self.analyses_cache.invalidate_analysis(LivenessAnalysis)
            # should be ok to be reevaluted
            # self.expression_analysis.analyze()
            self.expression_analysis = self.analyses_cache.force_analysis(
                CSEAnalysis
            )  # type: ignore

    # return instruction and to which instruction it could
    # replaced by
    def _find_replaceble(self) -> dict[IRInstruction, IRInstruction]:
        res: dict[IRInstruction, IRInstruction] = dict()

        for bb in self.function.get_basic_blocks():
            for inst in bb.instructions:
                # skip instruction that for sure
                # wont be substituted
                if (
                    inst.opcode in UNINTERESTING_OPCODES
                    or inst.opcode in NONIDEMPOTENT_INSTRUCTIONS
                ):
                    continue
                inst_expr = self.expression_analysis.get_expression(inst)
                # heuristic to not replace small expressions
                # basic block bounderies (it can create better codesize)
                if inst_expr.inst != inst and (
                    inst_expr.depth > 1 or inst.parent == inst_expr.inst.parent
                ):
                    res[inst] = inst_expr.inst

        return res

    def _replace(self, replace_dict: dict[IRInstruction, IRInstruction]):
        for orig, to in replace_dict.items():
            self._replace_inst(orig, to)

    def _replace_inst(self, orig_inst: IRInstruction, to_inst: IRInstruction):
        if orig_inst.output is not None:
            orig_inst.opcode = "store"
            assert isinstance(to_inst.output, IRVariable), f"not var {to_inst}"
            orig_inst.operands = [to_inst.output]
        else:
            orig_inst.opcode = "nop"
            orig_inst.operands = []
