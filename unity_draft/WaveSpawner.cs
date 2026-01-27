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
            public int unlockLevel;
        }

        public GameBalanceConfig balance;
        public List<ThreatEntry> threatTable = new()
        {
            new ThreatEntry{ typeId = "basic", cost = 1, weight = 50, unlockLevel = 0 },
            new ThreatEntry{ typeId = "fast", cost = 2, weight = 20, unlockLevel = 0 },
            new ThreatEntry{ typeId = "ranged", cost = 3, weight = 16, unlockLevel = 0 },
            new ThreatEntry{ typeId = "suicide", cost = 2, weight = 14, unlockLevel = 0 },
            new ThreatEntry{ typeId = "buffer", cost = 3, weight = 10, unlockLevel = 0 },
            new ThreatEntry{ typeId = "shielder", cost = 3, weight = 10, unlockLevel = 0 },
            new ThreatEntry{ typeId = "strong", cost = 4, weight = 8, unlockLevel = 0 },
            new ThreatEntry{ typeId = "tank", cost = 4, weight = 6, unlockLevel = 0 },
            new ThreatEntry{ typeId = "ravager", cost = 5, weight = 8, unlockLevel = 0 },
            new ThreatEntry{ typeId = "splinter", cost = 4, weight = 10, unlockLevel = 2 },
        };

        public float spawnInterval = 8f;
        public int enemyCap = 30;
        private float _timer;
        [Header("Budget Scaling (matches Python)")]
        public int threatBudgetBase = 6;
        public float threatBudgetExp = 1.18f;
        public int threatBudgetMin = 5;
        public float bossBudgetBonus = 1.5f;
        private int _levelIdx;
        private int _waveIndex = 0;
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
        [Header("Boss Waves")]
        public List<ThreatEntry> bossMinions = new()
        {
            new ThreatEntry{ typeId = "basic", cost = 1, weight = 30 },
            new ThreatEntry{ typeId = "ranged", cost = 2, weight = 20 },
            new ThreatEntry{ typeId = "fast", cost = 2, weight = 20 }
        };
        public float bossMinionInterval = 6f;
        private float _bossMinionTimer;

        private readonly Queue<string> _specialQueue = new();
        private bool _bossSpawned = false;
        private float _nextBanditTime = float.PositiveInfinity;
        public float CurrentBudget => _currentBudget;
        public float CurrentSpawnTimer => _timer;
        private int _currentBudget;

        public System.Action<string> OnSpawnRequested; // hook to actual spawn logic with typeId

        private void Update()
        {
            if (bossMode)
            {
                SpawnSpecialIfNeeded();
                SpawnBossMinions();
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
                SpawnWave();
                _waveIndex++;
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

        private void SpawnBossMinions()
        {
            _bossMinionTimer -= Time.deltaTime;
            if (_bossMinionTimer > 0f) return;
            _bossMinionTimer = bossMinionInterval;
            var entry = PickByWeight(bossMinions);
            if (string.IsNullOrEmpty(entry.typeId)) return;
            SpawnImmediate(entry.typeId);
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
            // Budgeted spawn
            var entry = PickByWeight(threatTable, _levelIdx);
            if (string.IsNullOrEmpty(entry.typeId)) return;
            if (_currentBudget < entry.cost) return;
            _currentBudget -= entry.cost;
            SpawnImmediate(entry.typeId);
        }

        private ThreatEntry PickByWeight(List<ThreatEntry> table = null, int levelIdx = 0)
        {
            var list = table ?? threatTable;
            int total = 0;
            foreach (var t in list)
            {
                if (levelIdx < t.unlockLevel) continue;
                total += t.weight;
            }
            if (total <= 0) return default;
            int r = Random.Range(0, total);
            int acc = 0;
            foreach (var t in list)
            {
                if (levelIdx < t.unlockLevel) continue;
                acc += t.weight;
                if (r < acc) return t;
            }
            return list[^1];
        }

        private void SpawnWave()
        {
            _currentBudget = CalcBudget(_levelIdx);
            int safety = 128;
            while (_currentBudget > 0 && safety-- > 0 && !bossMode)
            {
                var entry = PickByWeight(threatTable, _levelIdx);
                if (string.IsNullOrEmpty(entry.typeId)) break;
                if (_currentBudget < entry.cost) break;
                _currentBudget -= entry.cost;
                SpawnImmediate(entry.typeId);
                if (enemyCap > 0 && OnSpawnRequested == null && enemyFactory == null) break;
            }
        }

        public void ConfigureForLevel(Systems.GameManager gm, Systems.LevelFlow flow)
        {
            bossMode = gm != null && gm.bossLevel;
            twinBoss = gm != null && gm.twinBoss;
            banditAllowed = gm != null && gm.banditAllowed;
            _levelIdx = gm != null ? gm.currentLevelIndex : 0;
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
                if (twinBoss)
                {
                    _specialQueue.Enqueue(twinBossTypeId);
                    _specialQueue.Enqueue(twinBossTypeId);
                }
                else
                {
                    _specialQueue.Enqueue(bossTypeId);
                }
                _bossMinionTimer = bossMinionInterval;
            }
            _nextBanditTime = banditAllowed ? Time.time + banditFirstDelay : float.PositiveInfinity;
            _waveIndex = 0;
            _currentBudget = CalcBudget(_levelIdx);
        }

        public void RestoreState(float budget, float spawnTimer)
        {
            _currentBudget = Mathf.RoundToInt(budget);
            _timer = spawnTimer;
        }

        private Vector3 PickSpawnPos()
        {
            Vector3 center = spawnCenter != null ? spawnCenter.position : Vector3.zero;
            float ang = Random.Range(0f, Mathf.PI * 2f);
            float r = Random.Range(spawnRadius * 0.3f, spawnRadius);
            return center + new Vector3(Mathf.Cos(ang), Mathf.Sin(ang), 0f) * r;
        }

        private int CalcBudget(int levelIdx)
        {
            return Mathf.Max(threatBudgetMin,
                Mathf.RoundToInt(threatBudgetBase * Mathf.Pow(threatBudgetExp, levelIdx)));
        }
    }
}
