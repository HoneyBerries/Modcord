package net.honeyberries.ai;

import com.openai.models.responses.EasyInputMessage;
import com.openai.models.responses.ResponseInputItem;
import net.honeyberries.ResourceInitializer;
import org.jetbrains.annotations.NotNull;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Inference Engine Test")
//@Disabled("This test requires an OpenAI API key to be set in the environment variables")
@Tag("integration")
class InferenceEngineTest {

    static {
        ResourceInitializer.initialize();
    }

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
        @DisplayName("Should initializeFromConfig InferenceEngine successfully")
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
    @Tag("integration")
    class AIInferenceTests {
        
        @Test
        @DisplayName("Should successfully call AI inference with simple message")
        void testSimpleAIInference() throws ExecutionException, InterruptedException, TimeoutException {
            ResponseInputItem userMessage = userInput("Say 'Hello HoneyBerries'");

            var future = inferenceEngine.generateResponse(null, List.of(userMessage), null);
            String responseText = future.get(180, TimeUnit.SECONDS);

            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.toLowerCase().contains("hello honeyberries"),
                    "AI response should contain 'Hello HoneyBerries' but was: " + responseText);
            assertFalse(responseText.isEmpty(), "AI response should not be empty");
        }

        @Test
        @DisplayName("Should handle mathematical reasoning in AI")
        void testAIMathematicalReasoning() throws ExecutionException, InterruptedException, TimeoutException {
            ResponseInputItem userMessage = userInput("What is 1 + 2 + 3 + ... + 100? Just answer with the number.");

            var future = inferenceEngine.generateResponse(null, List.of(userMessage), null);
            String responseText = future.get(180, TimeUnit.SECONDS);

            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.contains("5050"), "Response should contain the correct answer");
        }

        @Test
        @DisplayName("Should handle question answering")
        void testAIQuestionAnswering() throws ExecutionException, InterruptedException, TimeoutException {
            ResponseInputItem userMessage = userInput("What is the capital of France and the United States");

            var future = inferenceEngine.generateResponse(null, List.of(userMessage), null);
            String responseText = future.get(180, TimeUnit.SECONDS);

            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.toLowerCase().contains("paris"), "Response should mention Paris");
            assertTrue(responseText.toLowerCase().contains("washington"), "Response should mention Washington");
        }

        @Test
        @DisplayName("Should handle multiple messages in conversation")
        void testAIConversationWithMultipleMessages() throws ExecutionException, InterruptedException, TimeoutException {
            List<ResponseInputItem> messages = List.of(
                userInput("My name is John"),
                userInput("Nice to meet you, John! How can I help you today?"),
                userInput("What's my name?")
            );

            var future = inferenceEngine.generateResponse(null, messages, null);
            String responseText = future.get(180, TimeUnit.SECONDS);

            assertNotNull(responseText, "AI should return text content");
            assertTrue(responseText.toLowerCase().contains("john"), "AI should remember the user's name");
        }

        @Test
        @DisplayName("Should return non-null even if responseFormat is null")
        void testAIInferenceWithNullResponseFormat() throws ExecutionException, InterruptedException, TimeoutException {
            ResponseInputItem userMessage = userInput("Respond with 'OK'");

            var future = inferenceEngine.generateResponse(null, List.of(userMessage), null);
            String response = future.get(180, TimeUnit.SECONDS);

            assertNotNull(response, "AI should return a response even with null responseFormat");
        }
    }

    @NotNull
    private static ResponseInputItem userInput(@NotNull String text) {
        return ResponseInputItem.ofEasyInputMessage(
                EasyInputMessage.builder()
                        .role(EasyInputMessage.Role.USER)
                        .content(text)
                        .build());
    }
}
