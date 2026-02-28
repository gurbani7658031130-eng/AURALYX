from pytgcalls import GroupCallFactory
from core.assistant import assistant


def test():
    try:
        factory = GroupCallFactory(
            assistant,
            mtproto_backend=GroupCallFactory.MTPROTO_CLIENT_TYPE.PYROGRAM,
        )
        _ = factory.get_group_call()
        print("PyTgCalls GroupCall initialized.")
        print("Smoke test passed.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test()
