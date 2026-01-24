using UnityEngine;
using System;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Central balance knobs translated from the current Pygame version.
    /// Keep values in sync with ZGame.py while porting systems.
    /// </summary>
    [CreateAssetMenu(fileName = "GameBalanceConfig", menuName = "ZGame/Balance")]
    public class GameBalanceConfig : ScriptableObject
    {
        [Header("Grid & World")]
        public int gridSize = 36;
        public float cellSize = 52f; // matches BASE_CELL_SIZE * WORLD_SCALE (~40 * 1.3)
        public float infoBarHeight = 40f;

        [Header("Player")]
        public float playerRadius = 0.30f; // as a fraction of cellSize
        public float playerSpeed = 4.5f;
        public float playerSpeedCap = 6.5f;

        [Header("Enemy Base")]
        public float enemyRadius = 0.30f;
        public float enemySpeed = 2f;
        public float enemySpeedMax = 4.5f;
        public int enemyAttack = 10;

        [Header("Enemy Footprint Multipliers")]
        public float tankSizeMult = 0.80f;
        public float shielderSizeMult = 0.80f;
        public float strongSizeMult = 0.70f;
        public float ravagerSizeMult = 1.25f;

        [Header("Coin Absorption Scaling")]
        public int coinTier1Max = 10;
        public int coinTier2Max = 20;
        public float coinScaleTier1 = 1.10f;
        public float coinScaleTier2 = 1.25f;
        public float coinScaleTier3 = 1.40f;
        public int spoilHpPer = 1;
        public int spoilAtkStep = 5;
        public int spoilSpdStep = 10;
        public float spoilSpdAdd = 0.5f;
        public float spoilSpdCap = 4.5f; // align with enemySpeedMax

        [Header("Spoils per Type (min/max)")]
        public EnemySpoilRange[] spoilRanges =
        {
            new EnemySpoilRange("basic",    1, 1),
            new EnemySpoilRange("fast",     1, 2),
            new EnemySpoilRange("strong",   2, 3),
            new EnemySpoilRange("tank",     2, 4),
            new EnemySpoilRange("ranged",   1, 3),
            new EnemySpoilRange("suicide",  1, 2),
            new EnemySpoilRange("buffer",   2, 3),
            new EnemySpoilRange("shielder", 2, 3),
            new EnemySpoilRange("bomber",   1, 2),
            new EnemySpoilRange("splinter", 1, 2),
            new EnemySpoilRange("splinterling", 0, 1),
            new EnemySpoilRange("ravager",  2, 5),
        };

        [Header("Obstacle/Nav Clearance")]
        [Tooltip("Radius (in world px) reserved when validating passages; set to enlarged basic footprint.")]
        public float navClearRadiusPx;

        private void OnValidate()
        {
            // Derived clearance: ~0.6 * cell footprint * tier3 scale * 0.5 for radius
            navClearRadiusPx = Mathf.Max(
                playerRadius * cellSize,
                0.6f * coinScaleTier3 * 0.5f * cellSize
            );
        }
    }

    [Serializable]
    public struct EnemySpoilRange
    {
        public string type;
        public int min;
        public int max;

        public EnemySpoilRange(string type, int min, int max)
        {
            this.type = type;
            this.min = min;
            this.max = max;
        }
    }
}
