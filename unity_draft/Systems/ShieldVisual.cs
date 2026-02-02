using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple shield overlay: enables a child sprite when shieldHp > 0.
    /// </summary>
    public class ShieldVisual : MonoBehaviour
    {
        public Enemy enemy;
        public Player player;
        public GameObject shieldSprite;
        public Color color = new Color(0.35f, 0.7f, 1f, 0.5f);

        private SpriteRenderer _sr;

        private void Awake()
        {
            if (enemy == null) enemy = GetComponent<Enemy>();
            if (player == null) player = GetComponent<Player>();
            if (shieldSprite != null) _sr = shieldSprite.GetComponent<SpriteRenderer>();
            if (_sr != null) _sr.color = color;
            if (shieldSprite != null) shieldSprite.SetActive(false);
        }

        private void Update()
        {
            int shieldHp = 0;
            if (enemy != null) shieldHp = enemy.shieldHp;
            if (player != null) shieldHp = player.shieldHp;
            bool active = shieldHp > 0;
            if (shieldSprite != null && shieldSprite.activeSelf != active)
            {
                shieldSprite.SetActive(active);
            }
        }
    }
}
