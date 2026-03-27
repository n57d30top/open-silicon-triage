import json
import os
import random
import uuid

# Paths
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_PATH = os.path.join(REPO_DIR, "corpus", "seed-corpus.json")

def generate_records(variant, count, is_winner, base_hpwl, base_wns, base_setup):
    records = []
    for _ in range(count):
        hpwl = base_hpwl * random.uniform(0.9, 1.1)
        wns = base_wns * random.uniform(0.8, 1.2) if base_wns < 0 else base_wns * random.uniform(0.9, 1.1)
        setup = int(base_setup * random.uniform(0.5, 1.5))
        
        # Adjust for losers
        if not is_winner:
            hpwl *= 1.3
            wns -= random.uniform(2.0, 5.0)
            setup += random.randint(50, 200)

        record = {
            "recordId": f"ost-syn-{uuid.uuid4().hex[:12]}",
            "schemaVersion": "open-silicon-triage.corpus.v1",
            "variant": variant,
            "outcome": "promoted_winner" if is_winner else "negative_evidence",
            "metrics": {
                "hpwlUm": round(hpwl, 2),
                "averageSinkWireLengthUm": round(hpwl / 30.0, 2),
                "setupWnsNs": round(wns, 2),
                "setupViolations": setup,
                "holdViolations": 0 if is_winner else random.randint(0, 50),
                "antennaViolations": 0 if is_winner else random.randint(0, 10),
            }
        }
        records.append(record)
    return records

def main():
    if not os.path.exists(CORPUS_PATH):
        print("Corpus not found")
        return

    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Generate picorv32 (small, moderate baseline)
    picorv_winners = generate_records("picorv32", 15, True, 250000, 0.5, 0)
    picorv_losers = generate_records("picorv32", 10, False, 250000, -1.0, 20)
    
    # Generate aes128 (very tiny, dense)
    aes_winners = generate_records("aes128", 12, True, 80000, 1.2, 0)
    aes_losers = generate_records("aes128", 8, False, 80000, -0.5, 10)

    # Generate generic multi-core (huge)
    mc_winners = generate_records("multi-core-soc", 5, True, 1500000, 0.1, 0)
    mc_losers = generate_records("multi-core-soc", 15, False, 1500000, -4.0, 500)

    data["records"].extend(picorv_winners + picorv_losers + aes_winners + aes_losers + mc_winners + mc_losers)

    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Added 65 new diverse records. Total records now: {len(data['records'])}")

if __name__ == "__main__":
    main()
