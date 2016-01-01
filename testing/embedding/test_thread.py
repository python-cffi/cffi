from testing.embedding.test_basic import EmbeddingTests


class TestThread(EmbeddingTests):
    def test_first_calls_in_parallel(self):
        self.prepare_module('add1')
        self.compile('thread1-test', ['_add1_cffi'], ['-pthread'])
        for i in range(5):
            output = self.execute('thread1-test')
            assert output == ("starting\n"
                              "preparing...\n" +
                              "adding 40 and 2\n" * 10 +
                              "done\n")
