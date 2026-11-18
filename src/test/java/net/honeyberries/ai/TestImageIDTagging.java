package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.models.responses.Response;
import com.openai.models.responses.ResponseCreateParams;
import com.openai.models.responses.ResponseInputContent;
import com.openai.models.responses.ResponseInputImage;
import com.openai.models.responses.ResponseInputItem;
import com.openai.models.responses.ResponseInputText;
import net.honeyberries.ResourceInitializer;
import net.honeyberries.config.AppConfig;
import net.honeyberries.util.TokenManager;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

//@Disabled("This test is for manual experimentation with image ID tagging and is not meant for automated test runs.")
@Tag("integration")
public class TestImageIDTagging {

    static {
        ResourceInitializer.initialize();
    }

    private final Logger logger = LoggerFactory.getLogger(TestImageIDTagging.class);

    private final String modelName;
    private final OpenAIClientAsync openAIClient;

    public TestImageIDTagging() {
        String apiKey = TokenManager.getOpenAIKey();
        String endpoint = AppConfig.getInstance().getAIEndpoint();
        this.modelName = AppConfig.getInstance().getAIModelName();

        this.openAIClient = OpenAIOkHttpClientAsync.builder()
                .apiKey(apiKey)
                .baseUrl(endpoint)
                .build();

        logger.info("InferenceEngine initialized with endpoint={}, model={}", endpoint, modelName);
    }

    private ResponseInputContent textPart(String text) {
        return ResponseInputContent.ofInputText(
            ResponseInputText.builder()
                .text(text)
                .build()
        );
    }

    private ResponseInputContent imagePart(String url) {
        return ResponseInputContent.ofInputImage(
            ResponseInputImage.builder()
                .detail(ResponseInputImage.Detail.AUTO)
                .imageUrl(url)
                .build()
        );
    }

    @Test
    public void testImageIDTagging() {
        String urlA = "https://pub-5b49e517109f46b7a979427602d9a9f0.r2.dev/home-banner.webp";
        String urlB = "https://pub-5b49e517109f46b7a979427602d9a9f0.r2.dev/minecraft-page-background.webp";
        String urlC = "https://pub-5b49e517109f46b7a979427602d9a9f0.r2.dev/gem-smp-background.webp";

        ResponseInputItem input = ResponseInputItem.ofMessage(ResponseInputItem.Message.builder()
            .role(ResponseInputItem.Message.Role.USER)
            .content(List.of(
                textPart("User 123 sent images A and B. user 456 sent images C and A."),

                textPart("This is Image C below:"),
                imagePart(urlC),

                textPart("This is Image A below:"),
                imagePart(urlA),

                textPart("This is Image B below:"),
                imagePart(urlB),


                textPart("Can you describe to me what each user send. what are their similarities? differences?")
            ))
            .build());

        ResponseCreateParams params = ResponseCreateParams.builder()
            .model(this.modelName)
            .inputOfResponse(List.of(input))
            .store(false)
            .build();

        Response result = openAIClient.responses().create(params).join();
        logger.info("Response: {}", result.output());
    }
}