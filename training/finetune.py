"""LoRA fine-tuning pipeline for BOWA.

Uses Parameter-Efficient Fine-Tuning (PEFT) to adapt a large base model
(e.g., Llama-3-8B) to BOWA's specific tone and tool-calling format
without requiring massive compute resources.
"""

import os
from pathlib import Path
import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

# Configuration
MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
DATASET_PATH = Path(__file__).parent / "data" / "bowa_dataset.jsonl"
OUTPUT_DIR = Path(__file__).parent / "bowa_model_adapters"


def get_model_id() -> str:
    """Allow Llama 3 or Mixtral without editing code."""
    return os.environ.get("BOWA_FINETUNE_MODEL", MODEL_ID)


def train():
    if not DATASET_PATH.exists():
        print(f"Dataset not found at {DATASET_PATH}. Run prepare_dataset.py first.")
        return

    print("Loading dataset...")
    dataset = load_dataset("json", data_files=str(DATASET_PATH), split="train")

    print("Configuring 4-bit quantization for consumer GPUs...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16
    )

    model_id = get_model_id()
    print(f"Loading base model: {model_id}")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    
    # Prepare model for LoRA
    model = prepare_model_for_kbit_training(model)
    
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print("Configuring SFT Trainer...")
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        optim="paged_adamw_32bit",
        save_steps=100,
        logging_steps=10,
        learning_rate=2e-4,
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        max_grad_norm=0.3,
        max_steps=int(os.environ.get("BOWA_FINETUNE_STEPS", "500")),
        warmup_ratio=0.03,
        group_by_length=True,
        lr_scheduler_type="cosine",
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=lora_config,
        dataset_text_field="text",
        max_seq_length=512,
        tokenizer=tokenizer,
        args=training_args,
    )

    print("Starting training...")
    trainer.train()
    
    print(f"Saving fine-tuned adapters to {OUTPUT_DIR}")
    trainer.model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    print("Training complete! You can now load these weights in the BOWA pipeline.")

if __name__ == "__main__":
    train()
