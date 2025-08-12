from queue import PriorityQueue

class Graph:
    def __init__(self):
        self.edges = {}  # 存储每个节点的邻居，比如 {'A': ['B', 'C']}
        self.weights = {}  # 存储每条边的权重，比如 {('A', 'B'): 2}

    def add_edge(self, from_node, to_node, weight):
        # 添加邻居
        if from_node not in self.edges:
            self.edges[from_node] = []
        self.edges[from_node].append(to_node)

        # 无向图还要加反向
        if to_node not in self.edges:
            self.edges[to_node] = []
        self.edges[to_node].append(from_node)

        # 记录边的权重
        self.weights[(from_node, to_node)] = weight
        self.weights[(to_node, from_node)] = weight  # 无向图反向也要

    def neighbors(self, node):
        return self.edges.get(node, [])

    def cost(self, from_node, to_node):
        return self.weights.get((from_node, to_node), float('inf'))

def heuristic(a, b):
    # 估算a到b的距离
    return abs(a[0]-b[0]) + abs(a[1]-b[1])

# def heuristic(a, b):
#     return 0


def a_star_search(graph, start, goal):
    frontier = PriorityQueue()
    frontier.put((0, start))
    came_from = {start: None}
    cost_so_far = {start: 0}

    while not frontier.empty():
        _, current = frontier.get()
        if current == goal:
            break

        for next in graph.neighbors(current):
            new_cost = cost_so_far[current] + graph.cost(current, next)
            if next not in cost_so_far or new_cost < cost_so_far[next]:
                cost_so_far[next] = new_cost
                priority = new_cost + heuristic(goal, next)
                frontier.put((priority, next))
                came_from[next] = current
    return came_from, cost_so_far

# Example
# came_from, cost_so_far = a_star_search(graph, 'A', 'D')
# print("从A到D的最短路径长度：", cost_so_far['D'])

# Output
def reconstruct_path(came_from, start, goal):
    path = []
    current = goal
    while current != start:
        path.append(current)
        current = came_from[current]
    path.append(start)
    path.reverse()
    return path

def main():
    # 创建一个示例图
    graph = Graph()
    graph.add_edge('A', 'B', 1)
    graph.add_edge('A', 'C', 4)
    graph.add_edge('B', 'C', 1)
    graph.add_edge('B', 'D', 3)

    # 设置起点和终点
    start = 'A'
    goal = 'D'

    # 调用A*算法
    came_from, cost_so_far = a_star_search(graph, start, goal)
    print(f"从{start}到{goal}的最短路径长度：", cost_so_far[goal])
    print("最短路径：", reconstruct_path(came_from, start, goal))

if __name__ == "__main__":
    main()
