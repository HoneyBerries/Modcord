package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionContentPart;
import com.openai.models.chat.completions.ChatCompletionContentPartImage;
import com.openai.models.chat.completions.ChatCompletionContentPartText;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import net.honeyberries.config.AppConfig;
import net.honeyberries.util.TokenManager;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

public class TestImageIDTagging {

    private final Logger logger = LoggerFactory.getLogger(TestImageIDTagging.class);

    private final String modelName;
    private final OpenAIClientAsync openAIClient;

    public TestImageIDTagging() {
        String apiKey = TokenManager.getOpenAIKey();
        String endpoint = AppConfig.getInstance().getAIEndpoint();
        this.modelName = "moonshotai/Kimi-K2.5";

        this.openAIClient = OpenAIOkHttpClientAsync.builder()
                .apiKey(apiKey)
                .baseUrl(endpoint)
                .build();

        logger.info("InferenceEngine initialized with endpoint={}, model={}", endpoint, modelName);
    }

    private ChatCompletionContentPart textPart(String text) {
        return ChatCompletionContentPart.ofText(
            ChatCompletionContentPartText.builder()
                .text(text)
                .build()
        );
    }

    private ChatCompletionContentPart imagePart(String url) {
        return ChatCompletionContentPart.ofImageUrl(
            ChatCompletionContentPartImage.builder()
                .imageUrl(ChatCompletionContentPartImage.ImageUrl.builder()
                    .url(url)
                    .build())
                .build()
        );
    }

    @Test
    public void testImageIDTagging() {
        String urlA = "https://honeyberries.net/assets/backgrounds/home-banner.webp";
        String urlB = "https://honeyberries.net/assets/backgrounds/minecraft-page-background.webp";
        String urlC = "https://honeyberries.net/assets/backgrounds/gem-smp-background.webp";

        ChatCompletionCreateParams params = ChatCompletionCreateParams.builder()
            .model(this.modelName)
            .addUserMessageOfArrayOfContentParts(List.of(
                textPart("User 123 sent images A and B. user 456 sent images C and A."),

                textPart("This is Image C below:"),
                imagePart(urlC),

                textPart("This is Image A below:"),
                imagePart(urlA),

                textPart("This is Image B below:"),
                imagePart(urlB),


                textPart("Can you describe to me what each user send. what are their similarities? differences?")
            ))
            .build();

        ChatCompletion result = openAIClient.chat().completions().create(params).join();
        logger.info("Response: {}", result.choices().getFirst().message().content().orElse("(no content)"));
    }
}