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
        public List<string> upgradePool = new() { "atk+1", "spd+5%", "range+10%", "shield+10", "crit+5%" };
        public List<string> ownedUpgrades = new();
        public int choicesCount = 3;
        public string pickerTitle = "Choose an upgrade";

        private string[] _currentChoices;

        private void Awake()
        {
            if (menu == null) menu = FindObjectOfType<MenuController>();
        }

        public void OfferLevelUp()
        {
            if (menu == null) return;
            _currentChoices = PickChoices();
            menu.BindLevelUpOptions(pickerTitle, _currentChoices);
            menu.onLevelUpChoice.AddListener(OnChoice);
            menu.ShowLevelUp();
        }

        private void OnChoice(int idx)
        {
            if (_currentChoices == null || idx < 0 || idx >= _currentChoices.Length) return;
            string choice = _currentChoices[idx];
            ownedUpgrades.Add(choice);
            menu.onLevelUpChoice.RemoveListener(OnChoice);
        }

        private string[] PickChoices()
        {
            if (upgradePool == null || upgradePool.Count == 0)
            {
                return new[] { "No upgrades available" };
            }
            int count = Mathf.Clamp(choicesCount, 1, upgradePool.Count);
            var list = new List<string>(upgradePool);
            var result = new List<string>();
            for (int i = 0; i < count; i++)
            {
                int idx = Random.Range(0, list.Count);
                result.Add(list[idx]);
                list.RemoveAt(idx);
            }
            return result.ToArray();
        }
    }
}
