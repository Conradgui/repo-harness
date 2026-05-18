"""Skills runtime compatibility module."""


def invoke_skill(runtime, name, arguments=""):
    return runtime.invoke_skill(name, arguments)

