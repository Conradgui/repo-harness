"""Small control-plane facade around model and tool execution."""


class RuntimeControlPlane:
    def __init__(self, runtime):
        self.runtime = runtime

    def complete_model(self, prompt, prompt_cache_key=None, prompt_cache_retention=None):
        return self.runtime.model_client.complete(
            prompt,
            self.runtime.max_new_tokens,
            prompt_cache_key=prompt_cache_key,
            prompt_cache_retention=prompt_cache_retention,
        )

    def execute_tool(self, name, args):
        return self.runtime.run_tool(name, args)
