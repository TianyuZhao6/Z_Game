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
        [Header("Special Flags")]
        public bool bossMode;
        public bool twinBoss;
        public string bossTypeId = "boss";
        public string twinBossTypeId = "boss_twin";
        public string banditTypeId = "bandit";
        public bool banditAllowed = false;
        public float banditFirstDelay = 60f;
        public float banditRespawnDelay = 45f;
        [Header("Spawn Targets")]
        public Systems.EnemyFactory enemyFactory;
        public Transform spawnCenter;
        public float spawnRadius = 14f;

        private readonly Queue<string> _specialQueue = new();
        private bool _bossSpawned = false;
        private float _nextBanditTime = float.PositiveInfinity;

        public System.Action<string> OnSpawnRequested; // hook to actual spawn logic with typeId

        private void Update()
        {
            if (bossMode)
            {
                SpawnSpecialIfNeeded();
                return;
            }

            if (banditAllowed && Time.time >= _nextBanditTime)
            {
                SpawnImmediate(banditTypeId);
                _nextBanditTime = Time.time + banditRespawnDelay;
            }

            _timer += Time.deltaTime;
            if (_timer >= spawnInterval)
            {
                _timer = 0f;
                TrySpawn();
            }
        }

        private void SpawnSpecialIfNeeded()
        {
            if (_bossSpawned) return;
            if (_specialQueue.Count == 0) return;
            var typeId = _specialQueue.Dequeue();
            SpawnImmediate(typeId);
            _bossSpawned = true;
        }

        private void SpawnImmediate(string typeId)
        {
            if (string.IsNullOrEmpty(typeId)) return;
            if (OnSpawnRequested != null)
            {
                OnSpawnRequested.Invoke(typeId);
            }
            else if (enemyFactory != null)
            {
                enemyFactory.Spawn(typeId, PickSpawnPos());
            }
        }

        private void TrySpawn()
        {
            // Placeholder: choose by weighted random and emit a request.
            var entry = PickByWeight();
            if (!string.IsNullOrEmpty(entry.typeId))
            {
                if (OnSpawnRequested != null)
                {
                    OnSpawnRequested.Invoke(entry.typeId);
                }
                else if (enemyFactory != null)
                {
                    enemyFactory.Spawn(entry.typeId, PickSpawnPos());
                }
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

        public void ConfigureForLevel(Systems.GameManager gm, Systems.LevelFlow flow)
        {
            bossMode = gm != null && gm.bossLevel;
            twinBoss = gm != null && gm.twinBoss;
            banditAllowed = gm != null && gm.banditAllowed;
            if (flow != null)
            {
                bossTypeId = flow.bossTypeId;
                twinBossTypeId = flow.twinBossTypeId;
                banditTypeId = flow.banditTypeId;
                banditFirstDelay = flow.banditFirstDelay;
                banditRespawnDelay = flow.banditRespawnDelay;
            }

            _specialQueue.Clear();
            _bossSpawned = false;
            if (bossMode)
            {
                _specialQueue.Enqueue(twinBoss ? twinBossTypeId : bossTypeId);
            }
            _nextBanditTime = banditAllowed ? Time.time + banditFirstDelay : float.PositiveInfinity;
        }

        private Vector3 PickSpawnPos()
        {
            Vector3 center = spawnCenter != null ? spawnCenter.position : Vector3.zero;
            float ang = Random.Range(0f, Mathf.PI * 2f);
            float r = Random.Range(spawnRadius * 0.3f, spawnRadius);
            return center + new Vector3(Mathf.Cos(ang), Mathf.Sin(ang), 0f) * r;
        }
    }
}
