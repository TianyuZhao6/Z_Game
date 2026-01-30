using UnityEngine;
using System.Collections.Generic;
using ZGame.UnityDraft.UI;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple level-up picker: chooses random upgrades from a pool and routes selection.
    /// Replace with real upgrade data later.
    /// </summary>
    public class LevelUpPicker : MonoBehaviour
    {
        public MenuController menu;
        [Tooltip("Pool of upgrade IDs; extend to ScriptableObjects later.")]
        public List<UpgradeDef> upgradePool = new();
        public List<string> ownedUpgrades = new();
        public int choicesCount = 3;
        public string pickerTitle = "Choose an upgrade";
        public Player player;
        public MetaProgression meta;

        private string[] _currentChoices;

        private void Awake()
        {
            if (menu == null) menu = FindObjectOfType<MenuController>();
            if (player == null) player = FindObjectOfType<Player>();
            if (meta == null) meta = FindObjectOfType<MetaProgression>();
        }

        public void OfferLevelUp()
        {
            if (menu == null) return;
            _currentChoices = PickChoices();
            menu.BindLevelUpOptions(pickerTitle, _currentChoices);
            menu.onLevelUpChoice.AddListener(OnChoice);
            menu.ShowLevelUp();
            Time.timeScale = 0f;
        }

        private void OnChoice(int idx)
        {
            if (_currentChoices == null || idx < 0 || idx >= _currentChoices.Length) return;
            string choice = _currentChoices[idx];
            ownedUpgrades.Add(choice);
            ApplyUpgrade(choice);
            menu.onLevelUpChoice.RemoveListener(OnChoice);
            menu.levelUpPanel?.SetActive(false);
            Time.timeScale = 1f;
        }

        private string[] PickChoices()
        {
            if (upgradePool == null || upgradePool.Count == 0)
            {
                return new[] { "No upgrades available" };
            }
            int count = Mathf.Clamp(choicesCount, 1, upgradePool.Count);
            var list = new List<UpgradeDef>(upgradePool);
            var result = new List<string>();
            for (int i = 0; i < count; i++)
            {
                int idx = Random.Range(0, list.Count);
                var up = list[idx];
                result.Add(up.displayName);
                list.RemoveAt(idx);
            }
            return result.ToArray();
        }

        private void ApplyUpgrade(string displayName)
        {
            var up = upgradePool.Find(u => u.displayName == displayName);
            if (up == null) return;
            switch (up.effect)
            {
                case UpgradeEffect.Attack:
                    if (player != null) player.attack += Mathf.RoundToInt(up.value);
                    break;
                case UpgradeEffect.Speed:
                    if (player != null) player.speed += up.value;
                    break;
                case UpgradeEffect.RangeMult:
                    if (player != null) player.rangeMult += up.value;
                    break;
                case UpgradeEffect.Shield:
                    if (player != null) player.shieldHp = Mathf.Max(player.shieldHp, Mathf.RoundToInt(up.value));
                    break;
                case UpgradeEffect.CritChance:
                    if (player != null) player.critChance += up.value;
                    break;
                case UpgradeEffect.CritMult:
                    if (player != null) player.critMult += up.value;
                    break;
                case UpgradeEffect.BonePlating:
                    Systems.StatusEffect.ApplyBonePlating(player.gameObject, up.value);
                    break;
                case UpgradeEffect.Carapace:
                    Systems.StatusEffect.ApplyCarapace(player.gameObject, up.value);
                    break;
                case UpgradeEffect.Coupon:
                    if (meta != null) meta.AddCoupon(Mathf.RoundToInt(up.value));
                    break;
                case UpgradeEffect.WantedBounty:
                    if (meta != null) meta.ActivateWanted(Mathf.RoundToInt(up.value));
                    break;
                case UpgradeEffect.RunCoins:
                    if (meta != null) meta.AddRunCoins(Mathf.RoundToInt(up.value));
                    break;
                case UpgradeEffect.BankCoins:
                    if (meta != null) meta.AddBankedCoins(Mathf.RoundToInt(up.value));
                    break;
            }
        }
    }
}
