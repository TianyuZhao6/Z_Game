using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Level/boss scheduling, twin boss toggle, bandit spawn toggle, biome selection.
    /// Replace with data-driven configs as you flesh out content.
    /// </summary>
    public class LevelFlow : MonoBehaviour
    {
        public int bossEveryNLevels = 5; // matches Python's BOSS_EVERY_N_LEVELS
        public HashSet<int> twinBossLevels = new HashSet<int> { 4 }; // 0-based index for level 5
        public string[] biomes = new[] { "Domain of Wind", "Misty Forest", "Scorched Hell", "Bastion of Stone" };
        [Header("Special Spawns")]
        public string bossTypeId = "boss";
        public string twinBossTypeId = "boss_twin";
        public string banditTypeId = "bandit";
        public float banditFirstDelay = 60f;
        public float banditRespawnDelay = 45f;
        public float banditChancePerWave = 0.28f;
        public int banditMinLevel = 2;
        [Header("Biome Buffs")]
        public List<BiomeBuff> biomeBuffs = new()
        {
            new BiomeBuff("Domain of Wind", playerSpeedMult:1.05f, enemySpeedMult:1.05f, enemyHpMult:1.0f, spoilBonus:0),
            new BiomeBuff("Misty Forest",   playerSpeedMult:1.0f,  enemySpeedMult:0.95f, enemyHpMult:1.0f, spoilBonus:0),
            new BiomeBuff("Scorched Hell",  playerSpeedMult:1.0f,  enemySpeedMult:1.0f,  enemyHpMult:1.1f, spoilBonus:1),
            new BiomeBuff("Bastion of Stone", playerSpeedMult:0.95f, enemySpeedMult:1.0f, enemyHpMult:1.15f, spoilBonus:0),
        };

        private bool _capturedBase;
        private float _baseEnemySpeed;
        private float _baseEnemyHp;
        private float _basePlayerSpeed;

        public bool IsBossLevel(int levelIdxZeroBased)
        {
            return ((levelIdxZeroBased + 1) % bossEveryNLevels) == 0;
        }

        public bool UseTwinBoss(int levelIdxZeroBased)
        {
            return twinBossLevels.Contains(levelIdxZeroBased);
        }

        public bool ShouldSpawnBandit(int levelIdxZeroBased)
        {
            // Placeholder: allow bandit every level > 0
            return levelIdxZeroBased > 0;
        }

        public string NextBiome(int levelIdxZeroBased)
        {
            if (biomes == null || biomes.Length == 0) return null;
            int idx = Mathf.Abs(levelIdxZeroBased) % biomes.Length;
            return biomes[idx];
        }

        private void CaptureBase(GameBalanceConfig balance)
        {
            if (_capturedBase || balance == null) return;
            _capturedBase = true;
            _baseEnemySpeed = balance.enemySpeed;
            _baseEnemyHp = balance.enemyAttack; // reuse attack field as a stand-in for hp scaling knob
            _basePlayerSpeed = balance.playerSpeed;
        }

        public void ClearBiomeBuffs(GameBalanceConfig balance)
        {
            if (!_capturedBase || balance == null) return;
            balance.enemySpeed = _baseEnemySpeed;
            balance.enemyAttack = Mathf.RoundToInt(_baseEnemyHp);
            balance.playerSpeed = _basePlayerSpeed;
        }

        public void ApplyBiomeBuffs(string biomeName, GameBalanceConfig balance)
        {
            CaptureBase(balance);
            ClearBiomeBuffs(balance);
            if (balance == null || string.IsNullOrEmpty(biomeName)) return;
            var buff = biomeBuffs.Find(b => b.name == biomeName);
            if (buff == null) return;
            balance.enemySpeed = _baseEnemySpeed * buff.enemySpeedMult;
            balance.enemyAttack = Mathf.RoundToInt(_baseEnemyHp * buff.enemyHpMult);
            balance.playerSpeed = _basePlayerSpeed * buff.playerSpeedMult;
        }

        public void ApplyBanditConfig(WaveSpawner spawner)
        {
            if (spawner == null) return;
            spawner.banditChancePerWave = banditChancePerWave;
            spawner.banditMinLevel = banditMinLevel;
        }
    }

    [System.Serializable]
    public class BiomeBuff
    {
        public string name;
        public float playerSpeedMult = 1f;
        public float enemySpeedMult = 1f;
        public float enemyHpMult = 1f;
        public int spoilBonus = 0;

        public BiomeBuff(string name, float playerSpeedMult, float enemySpeedMult, float enemyHpMult, int spoilBonus)
        {
            this.name = name;
            this.playerSpeedMult = playerSpeedMult;
            this.enemySpeedMult = enemySpeedMult;
            this.enemyHpMult = enemyHpMult;
            this.spoilBonus = spoilBonus;
        }
    }
}
