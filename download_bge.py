from huggingface_hub import snapshot_download

REPO = "gpustack/bge-m3-GGUF"
OUT_DIR = r"D:\LLM\llama.cpp\models"

print("Trying Q4_K_M first...")
try:
    path = snapshot_download(
        repo_id=REPO,
        allow_patterns="*Q4_K_M*.gguf",
        local_dir=OUT_DIR,
    )
    print("Downloaded:", path)
except Exception as e:
    print("Q4_K_M not found or failed:", e)
    print("Falling back to any GGUF...")
    path = snapshot_download(
        repo_id=REPO,
        allow_patterns="*.gguf",
        local_dir=OUT_DIR,
    )
    print("Downloaded:", path)
