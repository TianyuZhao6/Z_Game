using UnityEngine;
using ZGame.UnityDraft.Pathfinding;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple teleport with targeting/validation against blocked grid.
    /// </summary>
    public class PlayerTeleport : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public GridManager grid;
        public float maxRange = 6f;
        public KeyCode teleportKey = KeyCode.E;

        private void Awake()
        {
            if (grid == null) grid = FindObjectOfType<GridManager>();
        }

        private void Update()
        {
            if (Input.GetKeyDown(teleportKey))
            {
                TryTeleport();
            }
        }

        private void TryTeleport()
        {
            Vector3 mouse = Camera.main != null ? Camera.main.ScreenToWorldPoint(Input.mousePosition) : transform.position;
            mouse.z = 0f;
            Vector3 dir = mouse - transform.position;
            if (dir.magnitude > maxRange) dir = dir.normalized * maxRange;
            Vector3 targetPos = transform.position + dir;
            if (IsValid(targetPos))
            {
                transform.position = targetPos;
            }
        }

        private bool IsValid(Vector3 pos)
        {
            if (grid != null)
            {
                if (grid.IsBlocked(pos)) return false;
            }
            return true;
        }
    }
}
