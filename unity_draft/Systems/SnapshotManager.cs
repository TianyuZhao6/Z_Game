using UnityEngine;
using System.IO;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Minimal snapshot save/load for carry-over state. Uses JSON to disk.
    /// </summary>
    public class SnapshotManager : MonoBehaviour
    {
        public GameManager gameManager;
        public MetaProgression meta;
        public Player player;
        public LevelUpPicker levelUpPicker;
        public ShopSystem shop;
        public WaveSpawner waveSpawner;

        private string SnapshotPath => Path.Combine(Application.persistentDataPath, "zgame_snapshot.json");

        [System.Serializable]
        public class SnapshotData
        {
            public int levelIdx;
            public bool bossLevel;
            public bool twinBoss;
            public bool banditAllowed;
            public string biome;
            public int bankedCoins;
            public int runCoins;
            public int killCount;
            public int coupons;
            public int couponLevel;
            public int couponCap;
            public bool wantedActive;
            public int wantedBounty;
            public int wantedKillTarget;
            public int wantedPosterWaves;
            public int goldenInterestLevel;
            public int banditRadarLevel;
            public int rerollCount;
            public string[] shopInventory;
            public MetaProgression.ConsumableStack[] consumables;
            public int playerHp;
            public int playerMaxHp;
            public int playerLevel;
            public int playerXp;
            public float playerSpeed;
            public float playerRangeMult;
            public string[] ownedUpgrades;
            public string[] shopOwnedItems;
            public WaveState wave;
            public MetaState metaState;
        }

        [System.Serializable]
        public class WaveState
        {
            public int levelIdx;
            public float budget;
            public float spawnTimer;
        }

        [System.Serializable]
        public class MetaState
        {
            public int banked;
            public int run;
            public int kills;
            public int coupons;
            public bool wanted;
            public int wantedBounty;
            public int wantedKillTarget;
            public MetaProgression.ConsumableStack[] consumables;
        }

        public void SaveSnapshot()
        {
            var data = new SnapshotData();
            data.levelIdx = gameManager != null ? gameManager.currentLevelIndex : 0;
            if (gameManager != null)
            {
                data.bossLevel = gameManager.bossLevel;
                data.twinBoss = gameManager.twinBoss;
                data.banditAllowed = gameManager.banditAllowed;
                data.biome = gameManager.biome;
            }
            if (meta != null)
            {
                data.bankedCoins = meta.bankedCoins;
                data.runCoins = meta.runCoins;
                data.killCount = meta.killCount;
            data.coupons = meta.coupons;
            data.couponLevel = meta.couponLevel;
            data.couponCap = meta.couponCap;
            data.wantedActive = meta.wantedActive;
            data.wantedBounty = meta.wantedBounty;
            data.wantedKillTarget = meta.wantedKillTarget;
            data.wantedPosterWaves = meta.wantedPosterWaves;
            data.goldenInterestLevel = meta.goldenInterestLevel;
            data.banditRadarLevel = meta.banditRadarLevel;
            if (shop != null)
            {
                data.rerollCount = shop.RerollCount;
                data.shopInventory = shop.InventoryIds();
            }
            data.consumables = meta.consumables.ToArray();
            }
            if (player != null)
            {
                data.playerHp = player.hp;
                data.playerMaxHp = player.maxHp;
                data.playerLevel = player.level;
                data.playerXp = player.xp;
                data.playerSpeed = player.speed;
                data.playerRangeMult = player.rangeMult;
            }
            if (levelUpPicker != null)
            {
                data.ownedUpgrades = levelUpPicker.ownedUpgrades.ToArray();
            }
            if (shop != null)
            {
                data.shopOwnedItems = shop.ownedItems.ToArray();
            }
            if (waveSpawner != null)
            {
                data.wave = new WaveState
                {
                    levelIdx = data.levelIdx,
                    budget = waveSpawner.CurrentBudget,
                    spawnTimer = waveSpawner.CurrentSpawnTimer
                };
            }
            if (meta != null)
            {
                data.metaState = new MetaState
                {
                    banked = meta.bankedCoins,
                    run = meta.runCoins,
                    kills = meta.killCount,
                    coupons = meta.coupons,
                    wanted = meta.wantedActive,
                    wantedBounty = meta.wantedBounty,
                    wantedKillTarget = meta.wantedKillTarget,
                    consumables = meta.consumables.ToArray()
                };
            }
            var json = JsonUtility.ToJson(data, true);
            File.WriteAllText(SnapshotPath, json);
        }

        public bool LoadSnapshot()
        {
            if (!File.Exists(SnapshotPath)) return false;
            var json = File.ReadAllText(SnapshotPath);
            var data = JsonUtility.FromJson<SnapshotData>(json);
            if (data == null) return false;

            if (gameManager != null) gameManager.currentLevelIndex = data.levelIdx;
            if (gameManager != null)
            {
                gameManager.bossLevel = data.bossLevel;
                gameManager.twinBoss = data.twinBoss;
                gameManager.banditAllowed = data.banditAllowed;
                gameManager.biome = data.biome;
            }
            if (meta != null)
            {
                meta.bankedCoins = data.bankedCoins;
                meta.runCoins = data.runCoins;
                meta.killCount = data.killCount;
                meta.coupons = data.coupons;
                meta.couponLevel = data.couponLevel;
                meta.couponCap = data.couponCap;
                meta.wantedActive = data.wantedActive;
                meta.wantedBounty = data.wantedBounty;
                meta.wantedKillTarget = data.wantedKillTarget;
                meta.wantedPosterWaves = data.wantedPosterWaves;
                meta.goldenInterestLevel = data.goldenInterestLevel;
                meta.banditRadarLevel = data.banditRadarLevel;
                meta.consumables.Clear();
                if (data.consumables != null) meta.consumables.AddRange(data.consumables);
            }
            if (shop != null)
            {
                shop.SetRerollCount(data.rerollCount);
                shop.RestoreInventory(data.shopInventory);
                shop.ownedItems.Clear();
                if (data.shopOwnedItems != null) shop.ownedItems.AddRange(data.shopOwnedItems);
                shop.shopUi?.Populate();
            }
            if (player != null)
            {
                player.maxHp = data.playerMaxHp;
                player.hp = data.playerHp;
                player.level = data.playerLevel;
                player.xp = data.playerXp;
                player.speed = data.playerSpeed;
                player.rangeMult = data.playerRangeMult;
            }
            if (levelUpPicker != null)
            {
                levelUpPicker.ownedUpgrades.Clear();
                if (data.ownedUpgrades != null) levelUpPicker.ownedUpgrades.AddRange(data.ownedUpgrades);
            }
            if (shop != null)
            {
                shop.ownedItems.Clear();
                if (data.shopOwnedItems != null) shop.ownedItems.AddRange(data.shopOwnedItems);
            }
            if (waveSpawner != null && data.wave != null)
            {
                waveSpawner.RestoreState(data.wave.budget, data.wave.spawnTimer);
            }
            if (meta != null && data.metaState != null)
            {
                meta.bankedCoins = data.metaState.banked;
                meta.runCoins = data.metaState.run;
                meta.killCount = data.metaState.kills;
                meta.coupons = data.metaState.coupons;
                meta.wantedActive = data.metaState.wanted;
                meta.wantedBounty = data.metaState.wantedBounty;
                meta.wantedKillTarget = data.metaState.wantedKillTarget;
                meta.consumables.Clear();
                if (data.metaState.consumables != null) meta.consumables.AddRange(data.metaState.consumables);
            }
            return true;
        }

        public void ClearSnapshot()
        {
            if (File.Exists(SnapshotPath)) File.Delete(SnapshotPath);
        }
    }
}
