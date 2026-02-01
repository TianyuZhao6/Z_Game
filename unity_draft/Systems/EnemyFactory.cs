using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple factory/pool bridge for spawning enemies by string typeId.
    /// </summary>
    public class EnemyFactory : MonoBehaviour
    {
        [System.Serializable]
        public struct EnemyPrefabEntry
        {
            public string typeId;
            public Enemy prefab;
            public EnemyTypeConfig configOverride;
        }

        public GameBalanceConfig balance;
        public float spawnRadius = 10f;
        public EnemyPrefabEntry[] entries;
        public int currentLevelIndex = 0;
        public GameManager gameManager;

        private readonly Dictionary<string, EnemyPrefabEntry> _lookup = new();

        private void Awake()
        {
            foreach (var e in entries)
            {
                if (!string.IsNullOrEmpty(e.typeId) && !_lookup.ContainsKey(e.typeId))
                {
                    _lookup.Add(e.typeId, e);
                }
            }
        }

        public Enemy Spawn(string typeId, Vector3 position)
        {
            if (!_lookup.TryGetValue(typeId, out var entry) || entry.prefab == null) return null;
            var inst = Instantiate(entry.prefab, position, Quaternion.identity);
            var cfg = entry.configOverride != null ? entry.configOverride : inst.typeConfig;
            float cellSize = balance != null ? balance.cellSize : 52f;
            inst.Init(balance, cfg, cellSize, currentLevelIndex);
            ApplyBiomeOnSpawn(inst);
            return inst;
        }

        public Enemy SpawnAround(string typeId, Vector3 center)
        {
            float ang = Random.Range(0f, Mathf.PI * 2f);
            Vector3 pos = center + new Vector3(Mathf.Cos(ang), Mathf.Sin(ang), 0f) * spawnRadius;
            return Spawn(typeId, pos);
        }

        private void ApplyBiomeOnSpawn(Enemy e)
        {
            if (gameManager == null) gameManager = FindObjectOfType<GameManager>();
            var biome = gameManager != null ? gameManager.currentBiome : null;
            if (biome == null || e == null) return;
            if (biome.name == "Bastion of Stone")
            {
                bool isBoss = e.typeConfig != null && e.typeConfig.isBoss;
                bool isBandit = e.typeConfig != null && e.typeConfig.typeId == "bandit";
                float shieldFrac = (isBoss || isBandit) ? 0.25f : 0.50f;
                e.shieldHp = Mathf.RoundToInt(e.maxHp * shieldFrac);
            }
            if (biome.name == "Scorched Hell")
            {
                // Increase contact damage proxy: boost attack a bit
                e.attack = Mathf.RoundToInt(e.attack * 1.5f);
            }
        }
    }
}
