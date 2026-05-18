"""Tool execution boundary used by the runtime engine."""


def run_tool(runtime, name, args):
    return runtime.run_tool(name, args)

