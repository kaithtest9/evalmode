from local_client import remote_if_enabled, remote_func


@remote_func
def hello_world():
    print("Hello, world!")
    return 42

@remote_if_enabled(remote_url="http://127.0.0.1:5005/exec", print_stdout=True)
def test():
    print("Running remotely!")
    print("This is a test function.")
    import os
    print("Environment variable:", os.getenv("MY_ENV_VAR", "not set"))
    print("Current working directory:", hello_world())
    return 123

res = test()
print("Return value:", res)
