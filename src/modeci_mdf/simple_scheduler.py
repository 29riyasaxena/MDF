import sys

from modeci_mdf.standard_functions import mdf_functions, create_python_expression

from neuromllite.utils import evaluate as evaluate_params_nmllite
from neuromllite.utils import _params_info
from neuromllite.utils import FORMAT_NUMPY, FORMAT_TENSORFLOW

FORMAT_DEFAULT = FORMAT_NUMPY

def evaluate_expr(expr, func_params, array_format=FORMAT_DEFAULT, verbose=True):

    e = evaluate_params_nmllite(expr, func_params, array_format=array_format, verbose=verbose)
    if type(e) == str:
        raise Exception(
            "Error! Could not evaluate expression [%s] with params %s, returned [%s] which is a %s"
            % (expr, _params_info(func_params), e, type(e))
        )
    return e


class EvaluableFunction:
    def __init__(self, function, verbose=False):
        self.verbose = verbose
        self.function = function

    def evaluate(self, parameters, array_format=FORMAT_DEFAULT):

        expr = None
        for f in mdf_functions:
            if self.function.function == f:
                expr = create_python_expression(mdf_functions[f]["expression_string"])
        if not expr:
            raise "Unknown function: %s. Known functions: %s" % (
                self.function.function,
                mdf_functions.keys,
            )

        func_params = {}
        func_params.update(parameters)
        if self.verbose:
            print(
                "    ---  Evaluating %s with %s, i.e. [%s]"
                % (self.function, _params_info(func_params), expr)
            )
        for arg in self.function.args:
            func_params[arg] = evaluate_expr(
                self.function.args[arg], func_params, verbose=False, array_format=array_format
            )
            if self.verbose:
                print("      Arg %s became %s" % (arg, func_params[arg]))
        self.curr_value = evaluate_expr(expr, func_params, verbose=False, array_format=array_format)
        if self.verbose:
            print(
                "    Evaluated %s with %s =\t%s"
                % (self.function, _params_info(func_params), self.curr_value)
            )
        return self.curr_value


class EvaluableOutput:
    def __init__(self, output_port, verbose=False):
        self.verbose = verbose
        self.output_port = output_port

    def evaluate(self, parameters, array_format=FORMAT_DEFAULT):
        if self.verbose:
            print(
                "    Evaluating %s with %s "
                % (self.output_port, _params_info(parameters))
            )
        self.curr_value = evaluate_expr(
            self.output_port.value, parameters, verbose=False, array_format=array_format
        )
        print(
            "    Evaluated %s with %s \n       =\t%s"
            % (self.output_port, _params_info(parameters), self.curr_value)
        )
        return self.curr_value


class EvaluableInput:
    def __init__(self, input_port, verbose=False):
        self.verbose = verbose
        self.input_port = input_port
        self.curr_value = 0

    def set_input_value(self, value):
        if self.verbose:
            print("    Input value in %s set to %s" % (self.input_port.id, value))
        self.curr_value = value

    def evaluate(self, parameters, array_format=FORMAT_DEFAULT):
        print(
            "    Evaluated %s with %s =\t%s"
            % (self.input_port, _params_info(parameters), self.curr_value)
        )
        return self.curr_value


class EvaluableNode:
    def __init__(self, node, verbose=False):
        self.verbose = verbose
        self.node = node
        self.evaluable_inputs = {}
        self.evaluable_functions = {}
        self.evaluable_outputs = {}

        for ip in node.input_ports:
            rip = EvaluableInput(ip, self.verbose)
            self.evaluable_inputs[ip.id] = rip
        for f in node.functions:
            rf = EvaluableFunction(f, self.verbose)
            self.evaluable_functions[f.id] = rf
        for op in node.output_ports:
            rop = EvaluableOutput(op, self.verbose)
            self.evaluable_outputs[op.id] = rop

    def initialize(self):
        pass

    def evaluate_next(self, array_format=FORMAT_DEFAULT):

        print(
            "  Evaluating Node: %s with %s"
            % (self.node.id, _params_info(self.node.parameters))
        )
        curr_params = {}
        if self.node.parameters:
            curr_params.update(self.node.parameters)

        for eip in self.evaluable_inputs:
            i = self.evaluable_inputs[eip].evaluate(curr_params, array_format=array_format)
            curr_params[eip] = i
        for ef in self.evaluable_functions:
            curr_params[ef] = self.evaluable_functions[ef].evaluate(curr_params, array_format=array_format)
        for eop in self.evaluable_outputs:
            self.evaluable_outputs[eop].evaluate(curr_params, array_format=array_format)

    def get_output(self, id):
        for rop in self.evaluable_outputs:
            if rop == id:
                return self.evaluable_outputs[rop].curr_value


class EvaluableGraph:
    def __init__(self, graph, verbose=False):
        self.verbose = verbose
        print("\nInit graph: %s" % graph.id)
        self.graph = graph
        self.enodes = {}
        self.root_nodes = []

        for node in graph.nodes:
            if self.verbose:
                print("\n  Init node: %s" % node.id)
            en = EvaluableNode(node, self.verbose)
            self.enodes[node.id] = en
            self.root_nodes.append(node.id)

        for edge in graph.edges:
            self.root_nodes.remove(edge.receiver)

    def evaluate(self, array_format=FORMAT_DEFAULT):
        print(
            "\nEvaluating graph: %s, root nodes: %s, with array format %s" % (self.graph.id, self.root_nodes, array_format)
        )
        for rn in self.root_nodes:
            self.enodes[rn].evaluate_next(array_format=array_format)

        for edge in self.graph.edges:
            pre_node = self.enodes[edge.sender]
            post_node = self.enodes[edge.receiver]
            value = pre_node.evaluable_outputs[edge.sender_port].curr_value
            weight = 1 if not edge.parameters or not 'weight' in edge.parameters else edge.parameters['weight']
            print(
                "  Edge %s connects %s to %s, passing %s with weight %s"
                % (edge.id, pre_node.node.id, post_node.node.id, value, weight)
            )
            post_node.evaluable_inputs[edge.receiver_port].set_input_value(value * weight)
            post_node.evaluate_next(array_format=array_format)




def main(example_file, verbose=True):

    from modeci_mdf.utils import load_mdf, print_summary

    mod_graph = load_mdf(example_file).graphs[0]

    if verbose:
        print("Loaded Graph:")
        print_summary(mod_graph)

        print("------------------")
    eg = EvaluableGraph(mod_graph, verbose)
    eg.evaluate()


if __name__ == "__main__":

    example_file = "../../examples/Simple.json"
    verbose = True
    if len(sys.argv) == 2:
        example_file = sys.argv[1]
        verbose = True
        verbose = False

    main(example_file, verbose)
