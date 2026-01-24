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
    }
}
