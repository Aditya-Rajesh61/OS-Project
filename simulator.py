"""Deterministic, demand-paged memory model. No real memory is allocated."""

from dataclasses import asdict, dataclass, fields
from math import log2


@dataclass(frozen=True)
class Configuration:
    page_size: int = 1024
    virtual_pages: int = 16
    physical_frames: int = 4
    tlb_capacity: int = 4
    page_policy: str = "LRU"
    tlb_policy: str = "LRU"
    tlb_ns: int = 10
    memory_ns: int = 100
    fault_penalty_ns: int = 1_000_000

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a JSON object.")
        known = {field.name for field in fields(cls)}
        if set(data) - known:
            raise ValueError("Unknown configuration field.")
        config = cls(**data)
        ranges = {
            "virtual_pages": (4, 64), "physical_frames": (2, 16),
            "tlb_capacity": (1, 16), "tlb_ns": (1, 1000),
            "memory_ns": (1, 10000), "fault_penalty_ns": (0, 100_000_000),
        }
        for name, (low, high) in ranges.items():
            value = getattr(config, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name.replace('_', ' ')} must be an integer from {low} to {high}.")
        if type(config.page_size) is not int or config.page_size not in (256, 512, 1024, 2048, 4096):
            raise ValueError("Page size must be 256, 512, 1024, 2048, or 4096 bytes.")
        if config.virtual_pages not in (4, 8, 16, 32, 64):
            raise ValueError("Virtual pages must be a power of two from 4 to 64.")
        if config.physical_frames > config.virtual_pages:
            raise ValueError("Physical frames cannot exceed the number of virtual pages.")
        if config.tlb_capacity > config.virtual_pages:
            raise ValueError("TLB entries cannot exceed the number of virtual pages.")
        if config.page_policy not in ("LRU", "FIFO") or config.tlb_policy not in ("LRU", "FIFO"):
            raise ValueError("Replacement policy must be LRU or FIFO.")
        return config


class MemorySimulator:
    def __init__(self, config=None):
        self.config = config or Configuration()
        self.frames = [None] * self.config.physical_frames
        self.pages = {}
        self.tlb = {}
        self.history = []
        self.accesses = self.hits = self.faults = self.evictions = 0
        self.total_ns = self.baseline_ns = 0

    def translate(self, address):
        config = self.config
        if type(address) is not int or not 0 <= address < config.page_size * config.virtual_pages:
            raise ValueError(f"Address must be from 0 to {config.page_size * config.virtual_pages - 1}.")
        if self.accesses >= 10000:
            raise ValueError("This run has reached 10,000 accesses. Reset to start another run.")
        self.accesses += 1
        tick = self.accesses
        page, offset = divmod(address, config.page_size)
        hit = page in self.tlb
        fault = False
        evicted_page = None
        evicted_tlb = None
        steps = [{"title": "Split the address", "detail": f"{address} ÷ {config.page_size} → page {page}, offset {offset}."}]
        if hit:
            self.hits += 1
            frame = self.tlb[page]["frame"]
            self.tlb[page]["used"] = tick
            steps.append({"title": "TLB hit", "detail": f"Cached mapping: page {page} → frame {frame}. Page-table lookup skipped."})
        else:
            steps.append({"title": "TLB miss", "detail": f"Page {page} is not in the TLB. Look up its page-table entry."})
            if page in self.pages:
                frame = self.pages[page]["frame"]
                steps.append({"title": "Page is resident", "detail": f"The page table maps page {page} to frame {frame}."})
            else:
                fault = True
                self.faults += 1
                if None in self.frames:
                    frame = self.frames.index(None)
                    detail = f"Load page {page} from backing storage into free frame {frame}."
                else:
                    key = "used" if config.page_policy == "LRU" else "loaded"
                    evicted_page = min(self.pages, key=lambda p: self.pages[p][key])
                    frame = self.pages.pop(evicted_page)["frame"]
                    self.tlb.pop(evicted_page, None)  # A displaced page must never keep a stale mapping.
                    self.evictions += 1
                    detail = f"{config.page_policy} replaces page {evicted_page} in frame {frame} with page {page}; invalidate its TLB entry."
                self.frames[frame] = page
                self.pages[page] = {"frame": frame, "loaded": tick, "used": tick}
                steps.append({"title": "Page fault · load from storage", "detail": detail})
            if len(self.tlb) >= config.tlb_capacity:
                key = "used" if config.tlb_policy == "LRU" else "loaded"
                evicted_tlb = min(self.tlb, key=lambda p: self.tlb[p][key])
                self.tlb.pop(evicted_tlb)
            self.tlb[page] = {"frame": frame, "loaded": tick, "used": tick}
            steps.append({"title": "Update the TLB", "detail": f"Cache page {page} → frame {frame}." + (f" Replace TLB entry for page {evicted_tlb}." if evicted_tlb is not None else "")})
        self.pages[page]["used"] = tick
        physical_address = frame * config.page_size + offset
        penalty = config.fault_penalty_ns if fault else 0
        cost_ns = config.tlb_ns + config.memory_ns * (1 if hit else 2) + penalty
        self.total_ns += cost_ns
        self.baseline_ns += 2 * config.memory_ns + penalty
        steps.append({"title": "Access physical memory", "detail": f"({frame} × {config.page_size}) + {offset} = physical address {physical_address}."})
        event = {"index": tick, "address": address, "page": page, "offset": offset,
                 "frame": frame, "physical_address": physical_address, "tlb_hit": hit,
                 "page_fault": fault, "evicted_page": evicted_page, "evicted_tlb": evicted_tlb,
                 "cost_ns": cost_ns, "steps": steps}
        self.history.append(event)
        return event

    def snapshot(self):
        c = self.config
        count = self.accesses
        hit_rate = self.hits / count if count else 0
        return {
            "config": asdict(c),
            "address_bits": int(log2(c.page_size * c.virtual_pages)),
            "offset_bits": int(log2(c.page_size)),
            "page_bits": int(log2(c.virtual_pages)),
            "max_address": c.page_size * c.virtual_pages - 1,
            "page_table": [{"page": page, "present": page in self.pages, **self.pages.get(page, {"frame": None, "loaded": None, "used": None})} for page in range(c.virtual_pages)],
            "frames": [{"frame": frame, "page": page} for frame, page in enumerate(self.frames)],
            "tlb": [{"page": page, **entry} for page, entry in sorted(self.tlb.items(), key=lambda item: item[1]["loaded"])],
            "stats": {"accesses": count, "hits": self.hits, "misses": count - self.hits,
                      "faults": self.faults, "evictions": self.evictions,
                      "hit_rate": hit_rate * 100, "fault_rate": self.faults / count * 100 if count else 0,
                      "effective_ns": self.total_ns / count if count else 0,
                      "baseline_ns": self.baseline_ns / count if count else 0,
                      "translation_ns": c.tlb_ns + (2 - hit_rate) * c.memory_ns if count else 0,
                      "speedup": self.baseline_ns / self.total_ns if self.total_ns else 0},
            "history": list(reversed(self.history[-60:])),
            "last": self.history[-1] if self.history else None,
        }
