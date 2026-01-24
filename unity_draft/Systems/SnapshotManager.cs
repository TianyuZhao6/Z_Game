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

        private string SnapshotPath => Path.Combine(Application.persistentDataPath, "zgame_snapshot.json");

        [System.Serializable]
        public class SnapshotData
        {
            public int levelIdx;
            public int bankedCoins;
            public int runCoins;
            public int killCount;
            public int coupons;
            public bool wantedActive;
            public int wantedBounty;
            public int wantedKillTarget;
            public MetaProgression.ConsumableStack[] consumables;
            public int playerHp;
            public int playerMaxHp;
            public float playerSpeed;
            public float playerRangeMult;
        }

        public void SaveSnapshot()
        {
            var data = new SnapshotData();
            data.levelIdx = gameManager != null ? gameManager.currentLevelIndex : 0;
            if (meta != null)
            {
                data.bankedCoins = meta.bankedCoins;
                data.runCoins = meta.runCoins;
                data.killCount = meta.killCount;
                data.coupons = meta.coupons;
                data.wantedActive = meta.wantedActive;
                data.wantedBounty = meta.wantedBounty;
                data.wantedKillTarget = meta.wantedKillTarget;
                data.consumables = meta.consumables.ToArray();
            }
            if (player != null)
            {
                data.playerHp = player.hp;
                data.playerMaxHp = player.maxHp;
                data.playerSpeed = player.speed;
                data.playerRangeMult = player.rangeMult;
            }
            var json = JsonUtility.ToJson(data);
            File.WriteAllText(SnapshotPath, json);
        }

        public bool LoadSnapshot()
        {
            if (!File.Exists(SnapshotPath)) return false;
            var json = File.ReadAllText(SnapshotPath);
            var data = JsonUtility.FromJson<SnapshotData>(json);
            if (data == null) return false;

            if (gameManager != null) gameManager.currentLevelIndex = data.levelIdx;
            if (meta != null)
            {
                meta.bankedCoins = data.bankedCoins;
                meta.runCoins = data.runCoins;
                meta.killCount = data.killCount;
                meta.coupons = data.coupons;
                meta.wantedActive = data.wantedActive;
                meta.wantedBounty = data.wantedBounty;
                meta.wantedKillTarget = data.wantedKillTarget;
                meta.consumables.Clear();
                if (data.consumables != null) meta.consumables.AddRange(data.consumables);
            }
            if (player != null)
            {
                player.maxHp = data.playerMaxHp;
                player.hp = data.playerHp;
                player.speed = data.playerSpeed;
                player.rangeMult = data.playerRangeMult;
            }
            return true;
        }

        public void ClearSnapshot()
        {
            if (File.Exists(SnapshotPath)) File.Delete(SnapshotPath);
        }
    }
}
