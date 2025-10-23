# Multimodal Image Processing Update

## Overview
This update switches the image handling system from URL-based references to using **PIL (Pillow) Image objects** directly with vLLM's multimodal chat interface. This provides more reliable image processing and better integration with the AI model.

## Key Changes

### 1. **New Multimodal Message Format** (`ai_moderation_processor.py`)
- **Previous**: Images were referenced by URLs in text prompts
- **Current**: Images are loaded as PIL Image objects and passed directly to vLLM
- The system now uses vLLM's chat interface with multimodal content support

### 2. **Message Processing Flow**
The updated `messages_to_prompt()` method now:
1. Downloads images to local disk (unchanged)
2. Opens images using PIL/Pillow
3. Constructs vLLM-compatible multimodal content with:
   - Text descriptions of messages and context
   - PIL Image objects embedded directly in content
   - Metadata tracking which user sent which image

### 3. **vLLM Chat Interface** (`ai_core.py`)
Added new `generate_chat()` method that:
- Accepts list of message dictionaries (like OpenAI chat format)
- Supports multimodal content (text + images)
- Uses vLLM's native `inputs={"messages": ...}` API
- Maintains guided decoding with JSON schema enforcement

### 4. **Image Metadata Tracking**
Each image in the multimodal content includes:
- User ID (who sent the image)
- Message ID (which message contains the image)
- Index (order within the message)

This allows the AI to:
- Know exactly who sent which image
- Handle multiple images from multiple users
- Maintain context across multi-user conversations

## Technical Details

### Message Format Example
```python
{
    "role": "user",
    "content": [
        {
            "type": "text",
            "text": "Channel: 123456\n\nUser: john_doe (ID: 789)\nContent: Check this out!\n[Image: screenshot.png from message 999 by user 789]"
        },
        {
            "type": "image",
            "image": <PIL.Image.Image object>  # PIL Image directly
        }
    ]
}
```

### Advantages Over URL Method

1. **Reliability**: No dependency on external URLs or network connectivity during inference
2. **Performance**: Images are already cached locally, no additional network calls
3. **Security**: Images are validated and processed locally before being sent to model
4. **Flexibility**: PIL allows image preprocessing, resizing, format conversion
5. **vLLM Native**: Uses vLLM's official multimodal API as documented

## Image Flow Diagram

```
Discord Message
    ↓
Download to cache (existing)
    ↓
Load with PIL Image.open()
    ↓
Build multimodal content list
    ↓
Pass to vLLM chat interface
    ↓
Model processes with vision encoder
    ↓
Generate JSON response
    ↓
Cleanup cached files
```

## User Attribution

The system maintains clear attribution by:
1. Including user context in text descriptions
2. Labeling each image with user and message IDs
3. Preserving message order and structure
4. Allowing model to reason about who sent what

Example text content:
```
User: alice (ID: 123)
Message ID: 456
Content: Look at this meme
[Image: funny_cat.jpg from message 456 by user 123]

User: bob (ID: 789)
Message ID: 012
Content: That's hilarious!
[Image: laughing.gif from message 012 by user 789]
```

## Dependencies

- `Pillow` (PIL): Added to requirements.txt for image handling
- `vllm`: Already present, uses native multimodal chat API
- `json`: Standard library, for parsing payloads

## Configuration

No configuration changes required. The system automatically:
- Detects images in messages
- Downloads and caches them
- Converts to PIL format
- Passes to model
- Cleans up after inference

## Testing Recommendations

1. **Single Image**: Test with one user sending one image
2. **Multiple Images**: Test one user sending multiple images
3. **Multi-User**: Test multiple users each sending images
4. **Mixed Content**: Test messages with both text and images
5. **Image Formats**: Test various formats (PNG, JPG, GIF, WEBP)
6. **Error Handling**: Test with invalid/corrupted image URLs

## Backward Compatibility

The system maintains backward compatibility:
- Text-only messages work exactly as before
- Existing configuration remains valid
- No changes to database schema
- Same moderation output format

## Future Enhancements

Potential improvements:
1. Image preprocessing (resize, normalize)
2. Image quality/compression optimization
3. Batch image loading for performance
4. Image format validation and conversion
5. Support for animated images (GIF frames)

## References

- [vLLM Multimodal Documentation](https://docs.vllm.ai/en/latest/usage/multimodal_inputs.html)
- [Pillow Documentation](https://pillow.readthedocs.io/)
- [Qwen2-VL Model Documentation](https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct)
