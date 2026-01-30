using UnityEngine;
using UnityEngine.UI;
using TMPro;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Minimal HUD bindings: HP, coins, timer. Wire to your Player and game state.
    /// </summary>
    public class HUDController : MonoBehaviour
    {
        public Slider hpSlider;
        public TextMeshProUGUI hpText;
        public TextMeshProUGUI coinText;
        public TextMeshProUGUI timerText;
        [Header("Ability UI (optional)")]
        public TextMeshProUGUI teleportCdText;
        public TextMeshProUGUI blastCdText;
        public TextMeshProUGUI otherAbilityText;

        public void SetHp(int current, int max)
        {
            if (hpSlider)
            {
                hpSlider.maxValue = Mathf.Max(1, max);
                hpSlider.value = Mathf.Clamp(current, 0, max);
            }
            if (hpText)
            {
                hpText.text = $"{current}/{max}";
            }
        }

        public void SetCoins(int coins)
        {
            if (coinText) coinText.text = coins.ToString();
        }

        public void SetTimer(float secondsLeft)
        {
            if (!timerText) return;
            int s = Mathf.Max(0, Mathf.CeilToInt(secondsLeft));
            int m = s / 60;
            int sec = s % 60;
            timerText.text = $"{m:00}:{sec:00}";
        }

        public void SetAbilityCooldown(string id, float cd, float maxCd)
        {
            string text = maxCd <= 0.01f ? "Ready" : $"{Mathf.Max(0f, cd):0.0}s";
            switch (id)
            {
                case "teleport":
                    if (teleportCdText != null) teleportCdText.text = text;
                    break;
                case "blast":
                    if (blastCdText != null) blastCdText.text = text;
                    break;
                default:
                    if (otherAbilityText != null) otherAbilityText.text = $"{id}: {text}";
                    break;
            }
        }

        public void ShowBanner(string msg, float sec = 1.5f)
        {
            // minimal stub: reuse otherAbilityText as banner
            if (otherAbilityText == null) return;
            otherAbilityText.text = msg;
            // no coroutine here; caller can clear later
        }
    }
}
