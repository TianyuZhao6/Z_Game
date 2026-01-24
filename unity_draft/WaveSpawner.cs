using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Minimal wave spawner scaffolding mirroring threat budget flow.
    /// Hook into your actual enemy factory and balance weights.
    /// </summary>
    public class WaveSpawner : MonoBehaviour
    {
        [System.Serializable]
        public struct ThreatEntry
        {
            public string typeId;
            public int cost;
            public int weight;
        }

        public GameBalanceConfig balance;
        public List<ThreatEntry> threatTable = new()
        {
            new ThreatEntry{ typeId = "basic", cost = 1, weight = 50 },
            new ThreatEntry{ typeId = "fast", cost = 2, weight = 20 },
            new ThreatEntry{ typeId = "ranged", cost = 3, weight = 16 },
            new ThreatEntry{ typeId = "suicide", cost = 2, weight = 14 },
            new ThreatEntry{ typeId = "buffer", cost = 3, weight = 10 },
            new ThreatEntry{ typeId = "shielder", cost = 3, weight = 10 },
            new ThreatEntry{ typeId = "strong", cost = 4, weight = 8 },
            new ThreatEntry{ typeId = "tank", cost = 4, weight = 6 },
            new ThreatEntry{ typeId = "ravager", cost = 5, weight = 8 },
            new ThreatEntry{ typeId = "splinter", cost = 4, weight = 10 },
        };

        public float spawnInterval = 8f;
        public int enemyCap = 30;
        private float _timer;

        public System.Action<string> OnSpawnRequested; // hook to actual spawn logic with typeId

        private void Update()
        {
            _timer += Time.deltaTime;
            if (_timer >= spawnInterval)
            {
                _timer = 0f;
                TrySpawn();
            }
        }

        private void TrySpawn()
        {
            // Placeholder: choose by weighted random and emit a request.
            var entry = PickByWeight();
            if (!string.IsNullOrEmpty(entry.typeId))
            {
                OnSpawnRequested?.Invoke(entry.typeId);
            }
        }

        private ThreatEntry PickByWeight()
        {
            int total = 0;
            foreach (var t in threatTable) total += t.weight;
            if (total <= 0) return default;
            int r = Random.Range(0, total);
            int acc = 0;
            foreach (var t in threatTable)
            {
                acc += t.weight;
                if (r < acc) return t;
            }
            return threatTable[^1];
        }
    }
}
