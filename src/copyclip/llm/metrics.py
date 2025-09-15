import json
import time
import os
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict

@dataclass
class LLMMetrics:
    timestamp: str
    provider: str
    model: str
    operation: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    error: Optional[str] = None

class MetricsCollector:
    def __init__(self, log_file: str = "copyclip_metrics.jsonl"):
        self.log_file = log_file
        self.session_start = time.time()
        self.metrics = []
        
    def log_llm_call(self, provider: str, model: str, operation: str,
                     input_text: str, output_text: str, latency_ms: int,
                     cache_hit: bool = False, error: Optional[str] = None):
        """Registra métricas de cada llamada LLM."""
        
        # Cálculo de tokens (aproximado si no hay tiktoken)
        input_tokens = len(input_text.split()) * 1.3
        output_tokens = len(output_text.split()) * 1.3 if output_text else 0
        
        # Cálculo de costo
        cost = self._calculate_cost(provider, model, input_tokens, output_tokens)
        
        metric = LLMMetrics(
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model,
            operation=operation,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            total_tokens=int(input_tokens + output_tokens),
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            error=error
        )
        
        self.metrics.append(metric)
        
        # Escribir a archivo inmediatamente
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(asdict(metric)) + '\n')
        
        # Log en consola si está en modo debug
        if os.getenv("COPYCLIP_DEBUG"):
            print(f"[METRICS] {provider}/{model}: {operation} - "
                  f"{metric.total_tokens} tokens, ${cost:.4f}, "
                  f"{latency_ms}ms {'(CACHED)' if cache_hit else ''}",
                  file=sys.stderr)
    
    def _calculate_cost(self, provider: str, model: str, 
                       input_tokens: float, output_tokens: float) -> float:
        """Calcula el costo basado en el proveedor y modelo."""
        # Precios por millón de tokens
        pricing = {
            'deepseek': {'input': 0.14, 'output': 0.28},
            'openai': {
                'gpt-4o-mini': {'input': 0.15, 'output': 0.60},
                'gpt-4o': {'input': 2.50, 'output': 10.00}
            },
            'anthropic': {
                'claude-3-5-sonnet': {'input': 3.00, 'output': 15.00}
            }
        }
        
        provider_pricing = pricing.get(provider.lower(), {})
        if isinstance(provider_pricing, dict) and 'input' in provider_pricing:
            model_pricing = provider_pricing
        else:
            model_pricing = provider_pricing.get(model, {'input': 0, 'output': 0})
        
        input_cost = (input_tokens / 1_000_000) * model_pricing.get('input', 0)
        output_cost = (output_tokens / 1_000_000) * model_pricing.get('output', 0)
        
        return input_cost + output_cost
    
    def print_summary(self):
        """Imprime resumen de la sesión."""
        if not self.metrics:
            return
        
        total_tokens = sum(m.total_tokens for m in self.metrics)
        total_cost = sum(m.cost_usd for m in self.metrics)
        total_time = sum(m.latency_ms for m in self.metrics) / 1000
        cache_hits = sum(1 for m in self.metrics if m.cache_hit)
        
        print("\n" + "="*60, file=sys.stderr)
        print("📊 SESSION METRICS SUMMARY", file=sys.stderr)
        print("="*60, file=sys.stderr)
        print(f"Total API calls: {len(self.metrics)}", file=sys.stderr)
        print(f"Cache hits: {cache_hits} ({cache_hits/len(self.metrics)*100:.1f}%)", 
              file=sys.stderr)
        print(f"Total tokens: {total_tokens:,}", file=sys.stderr)
        print(f"Total cost: ${total_cost:.3f}", file=sys.stderr)
        print(f"Total API time: {total_time:.1f}s", file=sys.stderr)
        print(f"Avg latency: {sum(m.latency_ms for m in self.metrics)/len(self.metrics):.0f}ms", 
              file=sys.stderr)
        
        # Breakdown por proveedor
        by_provider = {}
        for m in self.metrics:
            if m.provider not in by_provider:
                by_provider[m.provider] = {'calls': 0, 'tokens': 0, 'cost': 0}
            by_provider[m.provider]['calls'] += 1
            by_provider[m.provider]['tokens'] += m.total_tokens
            by_provider[m.provider]['cost'] += m.cost_usd
        
        print("\nBy Provider:", file=sys.stderr)
        for provider, stats in by_provider.items():
            print(f"  {provider}: {stats['calls']} calls, "
                  f"{stats['tokens']:,} tokens, ${stats['cost']:.3f}", 
                  file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)

# Instancia global
metrics_collector = MetricsCollector()