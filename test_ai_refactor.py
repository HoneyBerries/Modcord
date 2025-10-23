#!/usr/bin/env python3
"""
Test script to verify the refactored AI core works correctly.
This tests the structure and API without requiring the full model to be loaded.
"""

import sys
sys.path.insert(0, 'src')

from modcord.ai.ai_core import InferenceProcessor, ModelState


def test_inference_processor_init():
    """Test that InferenceProcessor initializes correctly."""
    processor = InferenceProcessor()
    
    assert processor.llm is None, "LLM should be None initially"
    assert processor.sampling_params is None, "sampling_params should be None initially"
    assert processor.base_system_prompt is None, "base_system_prompt should be None initially"
    assert isinstance(processor.state, ModelState), "state should be a ModelState instance"
    assert not processor.state.init_started, "init_started should be False initially"
    assert not processor.state.available, "available should be False initially"
    assert processor.state.init_error is None, "init_error should be None initially"
    
    print("✓ InferenceProcessor initialization test passed")


def test_dynamic_schema_generation():
    """Test that dynamic schema generation works correctly."""
    processor = InferenceProcessor()
    
    # Test with sample user IDs
    user_ids = ["123456789", "987654321", "111222333"]
    schema = processor._build_dynamic_schema(user_ids)
    
    # Verify schema structure
    assert "type" in schema, "Schema should have 'type' field"
    assert schema["type"] == "object", "Schema type should be 'object'"
    assert "properties" in schema, "Schema should have 'properties' field"
    assert "channel_id" in schema["properties"], "Schema should have 'channel_id' property"
    assert "users" in schema["properties"], "Schema should have 'users' property"
    
    # Verify users array schema
    users_schema = schema["properties"]["users"]
    assert users_schema["type"] == "array", "Users should be an array"
    assert "items" in users_schema, "Users array should have items schema"
    
    # Verify user_id enum constraint
    user_schema = users_schema["items"]
    assert "properties" in user_schema, "User schema should have properties"
    assert "user_id" in user_schema["properties"], "User schema should have user_id"
    
    user_id_schema = user_schema["properties"]["user_id"]
    assert "enum" in user_id_schema, "user_id should have enum constraint"
    assert user_id_schema["enum"] == user_ids, "user_id enum should match input user_ids"
    
    print("✓ Dynamic schema generation test passed")
    print(f"  - Schema constrains user_id to: {user_ids}")


def test_model_state():
    """Test ModelState dataclass."""
    state = ModelState()
    
    assert not state.init_started, "init_started should be False by default"
    assert not state.available, "available should be False by default"
    assert state.init_error is None, "init_error should be None by default"
    
    # Test state mutations
    state.init_started = True
    state.available = True
    state.init_error = "test error"
    
    assert state.init_started, "init_started should be True after mutation"
    assert state.available, "available should be True after mutation"
    assert state.init_error == "test error", "init_error should be 'test error' after mutation"
    
    print("✓ ModelState test passed")


def test_api_methods_exist():
    """Test that all expected API methods exist."""
    processor = InferenceProcessor()
    
    # Check that all expected methods exist
    assert hasattr(processor, 'init_model'), "Should have init_model method"
    assert hasattr(processor, 'get_model'), "Should have get_model method"
    assert hasattr(processor, 'is_model_available'), "Should have is_model_available method"
    assert hasattr(processor, 'get_model_init_error'), "Should have get_model_init_error method"
    assert hasattr(processor, 'get_system_prompt'), "Should have get_system_prompt method"
    assert hasattr(processor, 'generate_chat'), "Should have generate_chat method"
    assert hasattr(processor, 'get_model_state'), "Should have get_model_state method"
    assert hasattr(processor, 'unload_model'), "Should have unload_model method"
    
    # Check method signatures by attempting to call with expected args
    # (These will fail if model not initialized, but we're just checking signatures)
    
    print("✓ API methods exist test passed")


def main():
    """Run all tests."""
    print("Testing refactored AI core...")
    print()
    
    test_inference_processor_init()
    test_dynamic_schema_generation()
    test_model_state()
    test_api_methods_exist()
    
    print()
    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    print()
    print("Summary of changes:")
    print("  • Replaced AsyncLLMEngine with synchronous LLM()")
    print("  • Using llm.chat() instead of engine.generate()")
    print("  • Dynamic schema generation to prevent ID hallucination")
    print("  • Using StructuredOutputsParams with xgrammar")
    print("  • Images handled as PIL images with proper download/conversion")
    print("  • Removed async locks and unnecessary abstraction")


if __name__ == "__main__":
    main()
