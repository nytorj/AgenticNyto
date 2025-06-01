import ollama

class OllamaClient:
    def __init__(self, host: str = 'http://localhost:11434', model: str = 'qwen2:7b'): # Changed qwen3:32b to qwen2:7b as it's a more common model
        self.client = ollama.Client(host=host)
        self.default_model = model

    def generate(self, prompt: str, model: str = None) -> str:
        if model is None:
            model = self.default_model

        try:
            response = self.client.chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt}]
            )
            return response['message']['content']
        except ollama.ResponseError as e:
            # Log the error or handle it more gracefully
            print(f"Ollama API Error: {e.status_code} - {e.error}")
            # Depending on requirements, could raise a custom exception
            # or return a specific error message.
            return f"Error: Could not generate text due to API error (status {e.status_code})."
        except Exception as e:
            # Catch other potential exceptions (e.g., network issues)
            print(f"An unexpected error occurred: {e}")
            return "Error: An unexpected error occurred during text generation."

if __name__ == '__main__':
    # Example usage (optional, for testing)
    # Make sure your Ollama server is running and the model is pulled:
    # ollama pull qwen2:7b
    try:
        client = OllamaClient() # Assumes Ollama running on default host and port

        # Test 1: Simple prompt with default model
        print("--- Test 1: Default Model ---")
        output = client.generate("Why is the sky blue?")
        print(f"Prompt: Why is the sky blue?\nResponse: {output}\n")

        # Test 2: Using a specific model (if available, otherwise will use default or error)
        # You might need to change 'phi3' to another model you have available
        print("--- Test 2: Specific Model (e.g., phi3) ---")
        # output_phi3 = client.generate("Explain quantum computing in simple terms", model='phi3')
        # print(f"Prompt: Explain quantum computing in simple terms\nResponse: {output_phi3}\n")
        # Commenting out specific model test as it might not be available for users
        # and the default model is already tested.

        # Test 3: Error handling (simulating an issue, e.g., wrong model name)
        print("--- Test 3: Error Handling (Non-existent model) ---")
        output_error = client.generate("Test prompt", model='nonexistentmodel:latest')
        print(f"Prompt: Test prompt (nonexistentmodel)\nResponse: {output_error}\n")

    except Exception as e:
        print(f"Error during example usage: {e}")
