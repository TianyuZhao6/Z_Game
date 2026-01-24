using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Per-enemy-type stat block. Create assets for basic, fast, strong, tank, ravager, etc.
    /// </summary>
    [CreateAssetMenu(fileName = "EnemyTypeConfig", menuName = "ZGame/EnemyType")]
    public class EnemyTypeConfig : ScriptableObject
    {
        [Header("Identity")]
        public string typeId = "basic";
        public string displayName = "Basic";
        public bool isElite = false;
        public bool isBoss = false;

        [Header("Stats")]
        public int baseHp = 30;
        public int attack = 10;
        public float speed = 2f;
        public float sizeMultiplier = 1.0f; // relative to base footprint (cellSize * 0.6)

        [Header("Visuals")]
        public Color color = new Color(1f, 0.35f, 0.35f);
        public Sprite sprite;
    }
}
