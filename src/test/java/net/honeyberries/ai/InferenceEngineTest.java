package net.honeyberries.ai;

import com.openai.models.chat.completions.ChatCompletionAssistantMessageParam;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import com.openai.models.chat.completions.ChatCompletionUserMessageParam;
import org.jetbrains.annotations.Nullable;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.concurrent.ExecutionException;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Inference Engine Test")
//@Disabled("This test requires an OpenAI API key to be set in the environment variables")
class InferenceEngineTest {
    
    private InferenceEngine inferenceEngine;
    
    @BeforeEach
    void setUp() {
        inferenceEngine = InferenceEngine.getInstance();
    }
    
    @Nested
    @DisplayName("getInstance() Tests")
    class GetInstanceTests {
        
        @Test
        @DisplayName("Should return the same instance (singleton pattern)")
        void testGetInstanceReturnsSingleton() {
            InferenceEngine instance1 = InferenceEngine.getInstance();
            InferenceEngine instance2 = InferenceEngine.getInstance();
            
            assertNotNull(instance1);
            assertSame(instance1, instance2, "getInstance should return the same singleton instance");
        }
    }
    
    @Nested
    @DisplayName("Initialization Tests")
    class InitializationTests {
        
        @Test
        @DisplayName("Should initialize InferenceEngine successfully")
        void testInitializationSuccessful() {
            assertNotNull(inferenceEngine, "InferenceEngine should be initialized");
        }
        
        @Test
        @DisplayName("Should have a valid model name configured")
        void testModelNameConfigured() {
            InferenceEngine engine = InferenceEngine.getInstance();
            assertNotNull(engine, "InferenceEngine should be instantiated");
        }
    }
    
    @Nested
    @DisplayName("Singleton Tests")
    class SingletonTests {
        
        @Test
        @DisplayName("getInstance should always return non-null")
        void testGetInstanceNotNull() {
            assertNotNull(InferenceEngine.getInstance());
        }
        
        @Test
        @DisplayName("Multiple calls to getInstance return the same instance")
        void testMultipleGetInstanceCalls() {
            InferenceEngine engine1 = InferenceEngine.getInstance();
            InferenceEngine engine2 = InferenceEngine.getInstance();
            InferenceEngine engine3 = InferenceEngine.getInstance();
            
            assertSame(engine1, engine2);
            assertSame(engine2, engine3);
        }
    }
    
    @Nested
    @DisplayName("AI Inference Tests (Real API Calls)")
    class AIInferenceTests {
        
        @Test
        @DisplayName("Should successfully call AI inference with simple message")
        void testSimpleAIInference() throws ExecutionException, InterruptedException {
            ChatCompletionMessageParam userMessage = ChatCompletionMessageParam.ofUser(
                ChatCompletionUserMessageParam.builder()
                    .content("Say 'Hello HoneyBerries'")
                    .build()
            );

            var future = inferenceEngine.generateResponse(List.of(userMessage), null);
            ChatCompletionAssistantMessageParam response = future.get();
            String responseText = extractAssistantText(response);

            assertNotNull(response, "AI should return a non-null response");
            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.toLowerCase().contains("hello honeyberries"), "AI response should contain 'Hello HoneyBerries'");
            assertFalse(responseText.isEmpty(), "AI response should not be empty");
        }

        @Test
        @DisplayName("Should handle mathematical reasoning in AI")
        void testAIMathematicalReasoning() throws ExecutionException, InterruptedException {
            ChatCompletionMessageParam userMessage = ChatCompletionMessageParam.ofUser(
                ChatCompletionUserMessageParam.builder()
                    .content("What is 1 + 2 + 3 + ... + 100? Just answer with the number.")
                    .build()
            );

            var future = inferenceEngine.generateResponse(List.of(userMessage), null);
            ChatCompletionAssistantMessageParam response = future.get();
            String responseText = extractAssistantText(response);

            assertNotNull(response, "AI should return a response");
            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.contains("5050"), "Response should contain the correct answer");
        }

        @Test
        @DisplayName("Should handle question answering")
        void testAIQuestionAnswering() throws ExecutionException, InterruptedException {
            ChatCompletionMessageParam userMessage = ChatCompletionMessageParam.ofUser(
                ChatCompletionUserMessageParam.builder()
                    .content("What is the capital of France and the United States")
                    .build()
            );

            var future = inferenceEngine.generateResponse(List.of(userMessage), null);
            ChatCompletionAssistantMessageParam response = future.get();
            String responseText = extractAssistantText(response);

            assertNotNull(response, "AI should return a response");
            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.toLowerCase().contains("paris"), "Response should mention Paris");
            assertTrue(responseText.toLowerCase().contains("washington"), "Response should mention Washington");
        }

        @Test
        @DisplayName("Should handle multiple messages in conversation")
        void testAIConversationWithMultipleMessages() throws ExecutionException, InterruptedException {
            List<ChatCompletionMessageParam> messages = List.of(
                ChatCompletionMessageParam.ofUser(
                    ChatCompletionUserMessageParam.builder()
                        .content("My name is John")
                        .build()
                ),
                ChatCompletionMessageParam.ofUser(
                    ChatCompletionUserMessageParam.builder()
                        .content("Nice to meet you, John! How can I help you today?")
                        .build()
                ),
                ChatCompletionMessageParam.ofUser(
                    ChatCompletionUserMessageParam.builder()
                        .content("What's my name?")
                        .build()
                )
            );

            var future = inferenceEngine.generateResponse(messages, null);
            ChatCompletionAssistantMessageParam response = future.get();
            String responseText = extractAssistantText(response);

            assertNotNull(response, "AI should return a response");
            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.toLowerCase().contains("john"), "AI should remember the user's name");
        }

        @Test
        @DisplayName("Should return non-null even if responseFormat is null")
        void testAIInferenceWithNullResponseFormat() throws ExecutionException, InterruptedException {
            ChatCompletionMessageParam userMessage = ChatCompletionMessageParam.ofUser(
                ChatCompletionUserMessageParam.builder()
                    .content("Respond with 'OK'")
                    .build()
            );

            var future = inferenceEngine.generateResponse(List.of(userMessage), null);
            ChatCompletionAssistantMessageParam response = future.get();

            assertNotNull(response, "AI should return a response even with null responseFormat");
        }
    }

    @Nullable
    private String extractAssistantText(@Nullable ChatCompletionAssistantMessageParam response) {
        if (response == null) {
            return null;
        }

        return response.content()
                .filter(ChatCompletionAssistantMessageParam.Content::isText)
                .map(ChatCompletionAssistantMessageParam.Content::asText)
                .orElse(null);
    }
}
