import threading
import time
import unittest

from app.core.script_types import (
    ScriptTypeRegistry,
    build_descriptor,
    build_legacy_fallback_provider_by_type_key,
)


class MaaFWScriptTypeRegistryTest(unittest.TestCase):
    def test_maafw_fallback_types_are_unavailable_plugins(self) -> None:
        for type_key in ("M9A",):
            provider = build_legacy_fallback_provider_by_type_key(type_key)
            self.assertIsNotNone(provider)
            descriptor = build_descriptor(provider)

            self.assertFalse(descriptor["is_builtin"])
            self.assertFalse(descriptor["available"])

    def test_bootstrap_is_thread_safe(self) -> None:
        registry = ScriptTypeRegistry()
        call_count = 0
        call_count_lock = threading.Lock()

        def register_builtin_providers() -> None:
            nonlocal call_count
            time.sleep(0.05)
            with call_count_lock:
                call_count += 1

        registry._register_builtin_providers = register_builtin_providers
        registry._load_entry_point_providers = lambda plugins_dir=None: None

        threads = [threading.Thread(target=registry.bootstrap) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(call_count, 1)
        self.assertTrue(registry._bootstrapped)


if __name__ == "__main__":
    unittest.main()
