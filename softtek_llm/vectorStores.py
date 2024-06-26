"""
# Vector Stores
Classes for managing vectors in a vector store.
"""

import os
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from pinecone import Pinecone, ServerlessSpec, Index
import requests
from faiss import IndexFlatIP, normalize_L2, read_index, write_index, serialize_index, deserialize_index
from pinecone.core.client.configuration import Configuration as OpenApiConfiguration
from supabase import create_client
from typing_extensions import override
import firebase_admin
from firebase_admin import storage

from softtek_llm.schemas import Vector


class VectorStore(ABC):
    """
    # Vector Store
    Abstract class for managing vectors in a vector store.

    ## Methods
    - `add(vectors: List[Vector], **kwargs: Any)`: Add vectors to the vector store. Must be implemented by a subclass.
    - `delete(ids: List[str], **kwargs: Any)`: Delete vectors from the vector store. Must be implemented by a subclass.
    - `search(vector: Vector | None = None, top_k: int = 1, **kwargs: Any) -> List[Vector]`: Search for vectors in the vector store. Must be implemented by a subclass.
    """

    def __init__(self):
        """Initializes the VectorStoreModel class."""
        super().__init__()

    @abstractmethod
    def add(self, vectors: List[Vector], **kwargs: Any):
        """
        Abstract method for adding the given vectors to the vectorstore.

        Args:
            `vectors` (List[Vector]): A List of Vector instances to add.
            `**kwargs` (Any): Additional arguments.

        Raises:
            NotImplementedError: The method must be implemented by a subclass.
        """
        raise NotImplementedError("add method must be overridden")

    @abstractmethod
    def delete(self, ids: List[str], **kwargs: Any):
        """
        Abstract method for deleting vectors from the VectorStore given a list of vector IDs

        Args:
            `ids` (List[str]): A List of Vector IDs to delete.
            `**kwargs` (Any): Additional arguments.

        Raises:
            NotImplementedError: The method must be implemented by a subclass.
        """
        raise NotImplementedError("delete method must be overridden")

    @abstractmethod
    def search(
        self, vector: Vector | None = None, top_k: int = 1, **kwargs: Any
    ) -> List[Vector]:
        """
        Abstract method for searching vectors that match the specified criteria.

        Args:
            `vector` (Vector | None, optional): The vector to use as a reference for the search. Defaults to `None`.
            `top_k` (int, optional): The number of results to return for each query. Defaults to 1.
            `**kwargs` (Any): Additional keyword arguments to customize the search criteria.

        Raises:
            NotImplementedError: If the search method is not overridden.
        """
        raise NotImplementedError("search method must be overridden")
    
    @property
    @abstractmethod
    def index() -> Index:
        ...

class PineconeVectorStore(VectorStore):
    """
    # Pinecone Vector Store
    Class for managing vectors in a Pinecone index. Inherits from VectorStore.

    ## Attributes
    - `api_key` (str): The API key for authentication with the Pinecone service.
    - `environment` (str): The Pinecone environment to use (e.g., "production" or "sandbox").
    - `index_name` (str): The name of the index where vectors will be stored and retrieved.

    ## Methods
    - `add(vectors: List[Vector], namespace: str | None = None, batch_size: int | None = None, show_progress: bool = True, **kwargs: Any)`: Add vectors to the index.
    - `delete(ids: List[str] | None = None, delete_all: bool | None = None, namespace: str | None = None, filter: Dict | None = None, **kwargs: Any)`: Delete vectors from the index.
    - `search(vector: Vector | None = None, id: str | None = None, top_k: int = 1, namespace: str | None = None, filter: Dict | None = None, **kwargs: Any) -> List[Vector]`: Search for vectors in the index.
    """

    @override
    def __init__(
        self, api_key: str, index_name: str):
        """
        Initialize a PineconeVectorStore object for managing vectors in a Pinecone index.

        Args:
            `api_key` (str): The API key for authentication with the Pinecone service.
            `environment` (str): The Pinecone environment to use (e.g., "production" or "sandbox").
            `index_name` (str): The name of the index where vectors will be stored and retrieved.
            `proxy` (str | None, optional): The proxy URL to use for requests. Defaults to None.

        Note:
            Make sure to use a valid API key and specify the desired environment and index name.
        """
        self.__pc = Pinecone(api_key=api_key)

        if index_name not in self.__pc.list_indexes().names():
            self.__pc.create_index(index_name, 1536, ServerlessSpec(cloud="aws", region="us-east-1"))

        self.__index = self.__pc.Index(index_name)

    @override
    def add(
        self,
        vectors: List[Vector],
        namespace: str | None = None,
        batch_size: int | None = None,
        show_progress: bool = True,
        **kwargs: Any,
    ):
        """Add vectors to the index.

        Args:
            `vectors` (List[Vector]): A list of Vector objects to add to the index. Note that each vector must have a unique ID.
            `namespace` (str | None, optional): The namespace to write to. If not specified, the default namespace is used. Defaults to None.
            `batch_size` (int | None, optional): The number of vectors to upsert in each batch. If not specified, all vectors will be upserted in a single batch. Defaults to None.
            `show_progress` (bool, optional): Whether to show a progress bar using tqdm. Applied only if batch_size is provided. Defaults to True.
            `**kwargs` (Any): Additional arguments.

        Raises:
            ValueError: If any of the vectors do not have a unique ID.
        """

        if "metadata" in kwargs:
            metadata:Dict = kwargs["metadata"]
        else:
            metadata:Dict = {}

        data_to_add = []
        ids = {}
        for vector in vectors:
            if not vector.id:
                raise ValueError("Vector ID cannot be empty when adding to Pinecone.")
            if ids.get(vector.id, None) is not None:
                raise ValueError(
                    f"Vector ID {vector.id} is not unique to this batch. Please make sure all vectors have unique IDs."
                )
            data_to_add.append((vector.id, vector.embeddings, {**metadata, **vector.metadata}))
            ids[vector.id] = 1

        self.__index.upsert(
            data_to_add,
            namespace=namespace,
            batch_size=batch_size,
            show_progress=show_progress,
            **kwargs,
        )

    @override
    def delete(
        self,
        ids: List[str] | None = None,
        delete_all: bool | None = None,
        namespace: str | None = None,
        filter: Dict | None = None,
        **kwargs: Any,
    ):
        """Delete vectors from the index.

        Args:
            `ids` (List[str] | None, optional): A list of vector IDs to delete. Defaults to None.
            `delete_all` (bool | None, optional): This indicates that all vectors in the index namespace should be deleted. Defaults to None.
            `namespace` (str | None, optional): The namespace to delete vectors from. If not specified, the default namespace is used. Defaults to None.
            `filter` (Dict | None, optional): If specified, the metadata filter here will be used to select the vectors to delete. This is mutually exclusive with specifying ids to delete in the `ids` param or using `delete_all=True`. Defaults to None.
            `**kwargs` (Any): Additional arguments.
        """
        self.__index.delete(
            ids=ids, delete_all=delete_all, namespace=namespace, filter=filter, **kwargs
        )

    @override
    def search(
        self,
        vector: Vector | None = None,
        id: str | None = None,
        top_k: int = 1,
        namespace: str | None = None,
        filter: Dict | None = None,
        **kwargs: Any,
    ) -> List[Vector]:
        """Search for vectors in the index.

        Args:
            `vector` (Vector | None, optional): The query vector. Each call can contain only one of the parameters `id` or `vector`. Defaults to None.
            `id` (str | None, optional): The unique ID of the vector to be used as a query vector. Each call can contain only one of the parameters `id` or `vector`. Defaults to None.
            `top_k` (int, optional): The number of results to return for each query. Defaults to 1.
            `namespace` (str | None, optional): The namespace to fetch vectors from. If not specified, the default namespace is used. Defaults to None.
            `filter` (Dict | None, optional): The filter to apply. You can use vector metadata to limit your search. Defaults to None.
            `**kwargs` (Any): Additional arguments.

        Returns:
            `vectors` (List[Vector]): A list of Vector objects containing the search results.
        """
        # TODO: Default queries and sparse_vector parameters. Is QueryVector class iterable?
        query_response = self.__index.query(
            vector=vector.embeddings if vector else None,
            id=id,
            top_k=top_k,
            namespace=namespace,
            filter=filter,
            include_values=True,
            include_metadata=True,
            **kwargs,
        )

        vectors = []
        for match in query_response.matches:
            metadata = vector.metadata if vector else {}
            if match.metadata:
                metadata.update(match.metadata)
            metadata.update({"score": match.score})
            vectors.append(
                Vector(
                    embeddings=match.values,
                    id=match.id,
                    metadata=metadata,
                )
            )

        return vectors

    def namespace_exists(self, namespace: str):
        namespaces = self.__index.describe_index_stats().namespaces
        return namespace in namespaces
    
    @property
    def index(self):
        return self.__index
    

class FAISSVectorStore(VectorStore):
    """
    # FAISS Vector Store
    Class for managing vectors in a FAISS index. Inherits from VectorStore.

    ## Attributes
    - `local_id` (Dict[str | None, List[Vector]]): A dictionary with the list of Vector objects of each namespace.
    - `index` (Dict[str | None, Any]): A dictionary with the FAISS index of each namespace.

    ## Methods
    - `__return_ids(ids: List[str], namespace: str | None) -> np.array`: Creates a Numpy array with the positional ids of the given Vectors ids.
    - `__return_embeddings(id: str, namespace: str | None) -> np.array`: Creates a Numpy array with the embeddings of the given Vector id.
    - `__return_vectors(ids: List[int], distance: List[float], namespace: str | None) -> List[Vector]`: Updates the score in the metadata of each Vector object, and creates a list of Vector objects given their positional ids.
    - `__remove_ids(ids: List[str], namespace: str | None)`: Removes the given Vector objects from the `local_id` list.
    - `add(vectors: List[Vector], namespace: str | None = None)`: Add vectors to the index.
    - `delete(ids: List[str] | None = None, delete_all: bool | None = None, namespace: str | None = None)`: Delete vectors from the index.
    - `search(vector: Vector | None = None, id: str | None = None, top_k: int = 1, namespace: str | None = None) -> List[Vector]`: Search for vectors in the index.
    - `save_local(dir_path: str = ".", namespace: str | None = None, save_all: bool = False)`: Save the index and the local_id objects from the given namespace or from all the namespaces.
    - `load_local(namespaces: List[str | None], dir_path: str = ".", d: int = 1536)`: Load the index and the local_id objects from the given namespace or from all the namespaces.
    """

    @override
    def __init__(
        self,
        local_id: Dict[str | None, List[Vector]] = None,
        index: Dict[str | None, Any] = None,
        d: int = 1536,
    ):
        print(firebase_admin._apps)
        """
        Initialize a FAISSVectorStore object to manage vectors in a FAISS index.

        Args:
            `local_id` (Dict[str | None, List[Vector]], optional): A dictionary with the list of Vector objects of each namespace.
            `index` (Dict[str | None, Any], optional): A dictionary with the FAISS index of each namespace.
            `d` (int, optional): The dimension of the Vector embeddings to be stored. Must coincide with the embeddings model used. The default is 1536.

        Raises:
            ValueError: If the user provides only one of the arguments.

        Note:
            The `None` key in both arguments refers to the general namespace.
        """
        if local_id and index:
            self.__local_id: Dict[str | None, List[Vector]] = local_id
            self.__index: Dict[str | None, Any] = index
        elif local_id is None and index is None:
            self.__local_id: Dict[str | None, List[Vector]] = {None: []}
            self.__index: Dict[str | None, Any] = {None: IndexFlatIP(d)}
        else:
            raise ValueError("You must provide both `local_id` and `index` or neither.")

    @property
    def local_id(self):
        """A dictionary with the list of Vector objects of each namespace."""
        return self.__local_id

    @property
    def index(self):
        """A dictionary with the index of each namespace."""
        return self.__index

    def __return_ids(self, ids: List[str], namespace: str | None) -> np.array:
        """
        Creates a Numpy array with the positional ids of the given Vectors ids.

        Args:
            `ids` (List[str]): A list with the ids of the Vector objects.
            `namespace` (str | None): The namespace where the Vector objects are stored.

        Returns:
            `ids_to_return` (np.array): An array of the positional ids of the Vectors objects.

        Raises:
            ValueError: If it does not find all the ids.
        """
        ids_to_return = [
            i for i, vector in enumerate(self.__local_id[namespace]) if vector.id in ids
        ]

        if len(ids_to_return) != len(ids):
            raise ValueError("Did not found all the ids provided.")

        return np.array(ids_to_return)

    def __return_embeddings(self, id: str, namespace: str | None) -> np.array:
        """
        Creates a Numpy array with the embeddings of the given Vector id.

        Args:
            `id` (str): The id of the Vector object.
            `namespace` (str | None): The namespace where the Vector objects are stored.

        Returns:
            `embeddings` (np.array): An array of the embeddings of the Vector object.

        Raises:
            ValueError: If it does not find the id.
        """
        embeddings = None

        for vector in self.__local_id[namespace]:
            if vector.id == id:
                embeddings = np.array([vector.embeddings.copy()], dtype=np.float32)
                normalize_L2(embeddings)
                break

        if embeddings is None:
            raise ValueError(f"Did not found the id {id} in the namespace {namespace}.")

        return embeddings

    def __return_vectors(
        self, ids: List[int], distance: List[float], namespace: str | None
    ) -> List[Vector]:
        """
        Updates the score in the metadata of each Vector object, and creates a list of Vector objects given their positional ids.

        Args:
            `ids` (List[int]): The positional ids of the Vector objects to return.
            `distance` (List[float]): The distance score of each Vector object.
            `namespace` (str | None): The namespace where the Vector objects are stored.

        Returns:
            `vectors_to_return` (List[Vector]): A list of Vector objects.
        """
        vectors_to_return = list()
        to_update = list()

        for i_, id in enumerate(ids):
            if id != -1:
                vector_ = None
                for i, vector in enumerate(self.__local_id[namespace]):
                    if id == i:
                        vector_ = vector
                        break

                metadata = vector_.metadata
                metadata.update({"score": distance[i_]})

                new_vector = Vector(
                    embeddings=vector_.embeddings, id=vector_.id, metadata=metadata
                )

                vectors_to_return.append(new_vector)

                to_update.append((id, new_vector))

        for i, vector in to_update:
            self.__local_id[namespace][i] = vector

        return vectors_to_return

    def __remove_ids(self, ids: List[str], namespace: str | None):
        """
        Removes the given Vector objects from the `local_id` list.

        Args:
            `ids` (List[int]): The positional ids of the Vector objects to return.
            `namespace` (str | None): The namespace where the Vector objects are stored.

        Raises:
            ValueError: if it does not find all the ids.
        """
        new_list = [
            vector for vector in self.__local_id[namespace] if vector.id not in ids
        ]

        if len(new_list) != len(ids):
            raise ValueError("Did not found all the ids provided.")

        self.__local_id[namespace] = new_list

    @override
    def add(
        self,
        vectors: List[Vector],
        namespace: str | None = None,
    ):
        """
        Adds the given Vector objects to the namespace.
        If the namespace does not exist, it is created with the given method. If no method is provided, `IndexFlatIP` is used.

        Args:
            `vectors` (List[Vector]): The list of Vector objects to be added.
            `namespace` (str | None, optional): The namespace where the Vector objects are going to be added. The default is `None`.

        Raises:
            ValueError: if an id is not unique within the given vectors or within the namespace.
            ValueError: if the dimension (d) of any of the vectors is different to the dimension set in the index.
        """
        if namespace not in self.__local_id.keys():
            self.__local_id[namespace] = list()
            self.__index[namespace] = IndexFlatIP(len(vectors[0].embeddings))

        ids = [vector.id for vector in self.__local_id[namespace]]
        ids_vector = list()

        for vector in vectors:
            if vector.id in ids or vector.id in ids_vector:
                raise ValueError(
                    f"The id {vector.id} is duplicated. The ids must be unique."
                )
            ids_vector.append(vector.id)

            if len(vector.embeddings) != self.__index[namespace].d:
                raise ValueError(
                    f"Vectors must be size {self.__index[namespace].d} but got size {len(vector.embeddings)} instead."
                )

        data_to_add = list()

        for vector in vectors:
            vector_to_add = np.array([vector.embeddings.copy()], dtype=np.float32)
            normalize_L2(vector_to_add)

            data_to_add.append(vector_to_add[0])

        self.__index[namespace].add(x=np.array(data_to_add))

        self.__local_id[namespace] += vectors

    @override
    def delete(
        self,
        ids: List[str] | None = None,
        delete_all: bool = False,
        namespace: str | None = None,
    ):
        """
        Deletes the given Vector objects or all the Vector objects of the given namespace.

        Args:
            `ids` (List[str] | None, optional): The list of Vector objects to be deleted from the given namespace. The default is `None`.
            `delete_all` (bool, optional): If set to `True`, all the Vector objects will be deleted from the given namespace. The default is `False`.
            `namespace` (str | None, optional): The namespace where the Vector objects are going to be deleted from. The default is `None`.

        Raises:
            ValueError: if the namespace does not exist.
            ValueError: if neither `ids` nor `delete_all` are given.

        Note:
            You must provide either `ids` or `delete_all`. And if both are given `ids` has the priority.
        """
        if namespace not in self.__local_id.keys():
            raise ValueError(f"The namespace {namespace} does not exist.")

        if ids is not None:
            ids_to_delete = self.__return_ids(ids=ids, namespace=namespace)
            self.__index[namespace].remove_ids(x=ids_to_delete)
            self.__remove_ids(ids=ids, namespace=namespace)
        elif delete_all:
            self.__index[namespace].reset()
            self.__local_id[namespace].clear()
        else:
            raise ValueError("You must provide either `ids` or `delete_all=True`")

    @override
    def search(
        self,
        vector: Vector | None = None,
        id: str | None = None,
        top_k: int = 1,
        namespace: str | None = None,
        **kwargs,
    ) -> List[Vector]:
        """
        Searches for the top `top_k` closest Vector objects to the given Vector object or id.

        Args:
            `vector` (Vector | None, optional): The Vector object to be compared to. The default is `None`.
            `id` (str | None, optional): The id of the Vector object to be compared to. The default is `None`.
            `top_k` (int, optional): The number of top Vector objects to be returned. The default is 1.
            `namespace` (str | None, optional): The namespace of the index that is going to be used. The default is `None`.

        Returns:
            `vectors`(List[Vector]): The list of top Vector objects.

        Raises:
            ValueError: if the namespace does not exist.
            ValueError: if neither `vector` nor `id` are given.

        Note:
            You must provide either `vector` or `id`. If both are given `vector` has the priority.
        """
        if "namespace" in kwargs:
            namespace = kwargs["namespace"]

        if namespace not in self.__local_id.keys():
            return []

        if self.__index[namespace].ntotal > 0:
            if vector:
                vector_to_search = np.array(
                    [vector.embeddings.copy()], dtype=np.float32
                )
                normalize_L2(vector_to_search)

                D, I = self.__index[namespace].search(x=vector_to_search, k=top_k)

                vectors = self.__return_vectors(
                    ids=I.tolist()[0], distance=D.tolist()[0], namespace=namespace
                )
            elif id:
                id_to_search = self.__return_embeddings(ids=[id], namespace=namespace)

                D, I = self.__index[namespace].search(x=id_to_search, k=top_k)

                vectors = self.__return_vectors(
                    ids=I.tolist()[0], distance=D.tolist()[0], namespace=namespace
                )
            else:
                raise ValueError("You must provide either `vector` or `id`.")
        else:
            vectors = []

        return vectors

    def save_local(
        self,
        dir_path: str = ".",
        namespace: str | None = None,
        save_all: bool = False,
    ):
        """
        Saves both the index and the local_id objects from the given namespace or from all the namespaces.
        If `folder_path` is not provided, it is stored in the current directory.
        If the folder does not exist, it is created.

        Args:
            `dir_path` (str, optional): The path to which all the files will be saved. The default is the current directory.
            `namespace` (str | None, optional): The namespace that will be saved. The default is `None`.
            `save_all` (bool, optional): If set to `True`, all the namespaces will be saved. The default is `False`.

        Raises:
            ValueError: if the namespace does not exist.

        Note:
            You must provide either `namespace` or `save_all`. If both are given `save_all` has the priority.
        """
        path = Path(dir_path)
        path.mkdir(exist_ok=True, parents=True)

        if save_all:
            for namespace_ in self.__index.keys():
                write_index(
                    self.__index[namespace_],
                    os.path.join(
                        path,
                        f"{'index' if namespace_ is None else namespace_ + '_index'}.faiss",
                    ),
                )

                with open(
                    os.path.join(
                        path,
                        f"{'index' if namespace_ is None else namespace_ + '_index'}.pkl",
                    ),
                    "wb",
                ) as f:
                    pickle.dump(self.__local_id[namespace_], f)
        else:
            if namespace not in self.__local_id.keys():
                raise ValueError(f"The namespace `{namespace}` does not exist.")

            write_index(
                self.__index[namespace],
                os.path.join(
                    path,
                    f"{'index' if namespace is None else namespace_ + '_index'}.faiss",
                ),
            )

            with open(
                os.path.join(
                    path,
                    f"{'index' if namespace is None else namespace + '_index'}.pkl",
                ),
                "wb",
            ) as f:
                pickle.dump(self.__local_id[namespace], f)

    @classmethod
    def load_local(
        cls,
        namespaces: List[str | None],
        dir_path: str = ".",
        d: int = 1536,
    ):
        """
        Creates a FAISSVectorStore from a list of `namespaces` stored in the `dir_path`.

        Args:
            `namespaces` (List[str | None]): The namespaces that will be retrieved.
            `dir_path` (str, optional): The path to which all the files will be retrieved. The default is the current directory.
            `d` (int, optional): The dimension of the Vector embeddings to be stored. Must coincide with the embeddings model used. The default is 1536.

        Raises:
            ValueError: if the given directory does not exist.
            ValueError: if something goes wrong with the files.

        Note:
            If you want to load the default index, include `None` in the list.
            Only if both the `.faiss` and `.pkl` files are found, the namespace is stored.
            If a namespace raises an error, it will be passed.
        """
        path = Path(dir_path)

        if not os.path.isdir(path):
            raise ValueError(f"The given directory does not exist: {dir_path}.")

        local_id_: Dict[str | None, List[Vector]] = dict()
        index_: Dict[str | None, Any] = dict()

        for namespace in namespaces:
            try:
                index = read_index(
                    str(
                        path
                        / f"{'index' if namespace is None else namespace + '_index'}.faiss"
                    )
                )

                with open(
                    path
                    / f"{'index' if namespace is None else namespace + '_index'}.pkl",
                    "rb",
                ) as f:
                    ids = pickle.load(f)

                index_[namespace] = index
                local_id_[namespace] = ids
            except Exception as e:
                raise RuntimeError(
                    f"Something wrong happend with the file(s) for the namespace `{namespace}`"
                )

        if None not in index_.keys():
            index_[None] = []
            local_id_[None] = IndexFlatIP(d)

        return cls(local_id_, index_)
    
    def save_firebase_storage(
        self,
        uid: str,
        file_id: str,
        file_path: str = "",
        namespace: str | None = None,
        save_all: bool = False,
    ):
        """
        Saves both the index and the local_id objects from the given namespace or from all the namespaces.
        If `folder_path` is not provided, it is stored in the current directory.
        If the folder does not exist, it is created.

        Args:
            `dir_path` (str, optional): The path to which all the files will be saved. The default is the current directory.
            `namespace` (str | None, optional): The namespace that will be saved. The default is `None`.
            `save_all` (bool, optional): If set to `True`, all the namespaces will be saved. The default is `False`.

        Raises:
            ValueError: if the namespace does not exist.

        Note:
            You must provide either `namespace` or `save_all`. If both are given `save_all` has the priority.
        """
        bucket = storage.bucket()

        if file_path == "":
            path = f"files/{uid}/documents/{file_id}"
        else :
            path = f"files/{uid}/documents/{file_path}/{file_id}" 

        if save_all:
            for namespace_ in self.__index.keys():

                chunk = serialize_index(self.__index[namespace_])
                pickled_index = pickle.dumps(chunk)
                index_blob = bucket.blob(f"{path}/{'index.pkl' if namespace_ is None else 'index_' + namespace_ + '.pkl'}")
                index_blob.upload_from_string(pickled_index, "application/octet-stream")

                pickled_local_id = pickle.dumps(self.__local_id[namespace_])
                local_id_blob = bucket.blob(f"{path}/{'local_id.pkl' if namespace_ is None else 'local_id_' + namespace_ + '.pkl'}")
                local_id_blob.upload_from_string(pickled_local_id, "application/octet-stream")

        else:
            if namespace not in self.__local_id.keys():
                raise ValueError(f"The namespace `{namespace}` does not exist.")

            chunk = serialize_index(self.__index[namespace])
            pickled_index = pickle.dumps(chunk)
            index_blob = bucket.blob(f"{path}/{'index.pkl' if namespace is None else 'index_' + namespace + '.pkl'}")
            index_blob.upload_from_string(pickled_index, "application/octet-stream")

            pickled_local_id = pickle.dumps(self.__local_id[namespace])
            local_id_blob = bucket.blob(f"{path}/{'local_id.pkl' if namespace is None else 'local_id_' + namespace + '.pkl'}")
            local_id_blob.upload_from_string(pickled_local_id, "application/octet-stream")

    @classmethod
    def load_firebase_storage(
        cls,
        uid: str,
        file_id: str,
        namespaces: List[str | None] = [None],
        file_path: str = "",
        d: int = 1536,
    ):
        """
        Creates a FAISSVectorStore from a list of `namespaces` stored in the `dir_path`.

        Args:
            `namespaces` (List[str | None]): The namespaces that will be retrieved.
            `dir_path` (str, optional): The path to which all the files will be retrieved. The default is the current directory.
            `d` (int, optional): The dimension of the Vector embeddings to be stored. Must coincide with the embeddings model used. The default is 1536.

        Raises:
            ValueError: if the given directory does not exist.
            ValueError: if something goes wrong with the files.

        Note:
            If you want to load the default index, include `None` in the list.
            Only if both the `.faiss` and `.pkl` files are found, the namespace is stored.
            If a namespace raises an error, it will be passed.
        """
        bucket = storage.bucket()
        
        local_id_: Dict[str | None, List[Vector]] = dict()
        index_: Dict[str | None, Any] = dict()

        if file_path == "":
            path = f"files/{uid}/documents/{file_id}"
        else :
            path = f"files/{uid}/documents/{file_path}/{file_id}" 

        for namespace in namespaces:
            try:
                index_blob = bucket.blob(f"{path}/{'index.pkl' if namespace is None else 'index_' + namespace + '.pkl'}")
                index = deserialize_index(pickle.loads(index_blob.download_as_bytes()))

                local_id_blob = bucket.blob(f"{path}/{'local_id.pkl' if namespace is None else 'local_id_' + namespace + '.pkl'}")
                ids = pickle.loads(local_id_blob.download_as_bytes())

                index_[namespace] = index
                local_id_[namespace] = ids
            except Exception as e:
                raise RuntimeError(
                    f"Something wrong happend with the file(s) for the namespace `{namespace}`"
                )

        if None not in index_.keys():
            index_[None] = []
            local_id_[None] = IndexFlatIP(d)

        return cls(local_id_, index_)


class SofttekVectorStore(VectorStore):
    """
    # Softtek Vector Store
    Class for managing vectors in a Softtek index. Inherits from VectorStore.

    ## Attributes
    - `api_key` (str): The API key for authentication with the Softtek service.

    ## Methods
    - `add(vectors: List[Vector], namespace: str | None = None, **kwargs: Any)`: Add vectors to the index.
    - `delete(ids: List[str] | None = None, delete_all: bool | None = None, namespace: str | None = None, filter: Dict | None = None, **kwargs: Any)`: Delete vectors from the index.
    - `search(vector: Vector | None = None, id: str | None = None, top_k: int = 1, namespace: str | None = None, filter: Dict | None = None, **kwargs: Any) -> List[Vector]`: Search for vectors in the index.
    """

    def __init__(self, api_key: str):
        """Initialize a SofttekVectorStore object for managing vectors in a Softtek index.

        Args:
            api_key (str): The API key for authentication with the LLMOPs service.
        """
        super().__init__()
        self.__api_key = api_key

    @property
    def api_key(self) -> str:
        """The API key for authentication with the LLMOPs service."""
        return self.__api_key

    @override
    def add(
        self,
        vectors: List[Vector],
        namespace: str | None = None,
        **kwargs: Any,
    ):
        """Add vectors to the index.

        Args:
            vectors (List[Vector]): A list of Vector objects to add to the index. Note that each vector must have a unique ID.
            namespace (str | None, optional): The namespace to write to. If not specified, the default namespace is used. Defaults to None.

        Raises:
            ValueError: If any of the vectors do not have a unique ID.
            ValueError: If any of the vectors do not have embeddings.
            Exception: If the request fails.
        """
        data_to_add = []
        ids = {}
        for vector in vectors:
            if not vector.id:
                raise ValueError("Vector ID cannot be empty when adding to Pinecone.")
            if ids.get(vector.id, None) is not None:
                raise ValueError(
                    f"Vector ID {vector.id} is not unique to this batch. Please make sure all vectors have unique IDs."
                )
            data_to_add.append((vector.id, vector.embeddings, vector.metadata))
            ids[vector.id] = 1

        kwargs.update({"vectors": data_to_add, "namespace": namespace})
        response = requests.post(
            "https://llm-api-stk.azurewebsites.net/vector-store/upsert",
            headers={"api-key": self.api_key},
            json=kwargs,
        )
        if response.status_code != 200:
            raise Exception(response.json()["detail"])

    @override
    def delete(
        self,
        ids: List[str] | None = None,
        delete_all: bool | None = None,
        namespace: str | None = None,
        filter: Dict | None = None,
        **kwargs: Any,
    ):
        """Delete vectors from the index.

        Args:
            ids (List[str] | None, optional): A list of vector IDs to delete. Defaults to None.
            delete_all (bool | None, optional): This indicates that all vectors in the index namespace should be deleted. Defaults to None.
            namespace (str | None, optional): The namespace to delete vectors from. If not specified, the default namespace is used. Defaults to None.
            filter (Dict | None, optional): If specified, the metadata filter here will be used to select the vectors to delete. This is mutually exclusive with specifying ids to delete in the `ids` param or using `delete_all=True`. Defaults to None.

        Raises:
            Exception: If the request fails.
        """
        kwargs.update(
            {
                "ids": ids,
                "delete_all": delete_all,
                "namespace": namespace,
                "filter": filter,
            }
        )
        response = requests.post(
            "https://llm-api-stk.azurewebsites.net/vector-store/delete",
            headers={"api-key": self.api_key},
            json=kwargs,
        )

        if response.status_code != 200:
            raise Exception(response.json()["detail"])

    @override
    def search(
        self,
        vector: Vector | None = None,
        id: str | None = None,
        top_k: int = 1,
        namespace: str | None = None,
        filter: Dict | None = None,
        **kwargs: Any,
    ) -> List[Vector]:
        """Search for vectors in the index.

        Args:
            vector (Vector | None, optional): The query vector. Each call can contain only one of the parameters `id` or `vector`. Defaults to None.
            id (str | None, optional): The unique ID of the vector to be used as a query vector. Each call can contain only one of the parameters `id` or `vector`. Defaults to None.
            top_k (int, optional): The number of results to return for each query. Defaults to 1.
            namespace (str | None, optional): The namespace to fetch vectors from. If not specified, the default namespace is used. Defaults to None.
            filter (Dict | None, optional): The filter to apply. You can use vector metadata to limit your search. Defaults to None.

        Raises:
            Exception: If the request fails.

        Returns:
            List[Vector]: A list of Vector objects containing the search results.
        """
        kwargs.update(
            {
                "vector": vector.embeddings if vector else None,
                "id": id,
                "top_k": top_k,
                "namespace": namespace,
                "filter": filter,
                "include_metadata": True,
                "include_values": True,
            }
        )
        response = requests.post(
            "https://llm-api-stk.azurewebsites.net/vector-store/query",
            headers={"api-key": self.api_key},
            json=kwargs,
        )

        if response.status_code != 200:
            raise Exception(response.json()["detail"])

        json_response = response.json()

        vectors = []
        for match in json_response["matches"]:
            metadata = vector.metadata if vector else {}
            match_metadata = match.get("metadata")
            if match_metadata:
                metadata.update(match_metadata)
            metadata.update({"score": match["score"]})
            vectors.append(
                Vector(
                    embeddings=match["values"],
                    id=match["id"],
                    metadata=metadata,
                )
            )

        return vectors


class SupabaseVectorStore(VectorStore):
    """
    # Supabase Vector Store
    Class for managing vectors in a Supabase table. Inherits from VectorStore.

    ## Attributes
    - `api_key` (str): The API key for authentication with the Supabase service.
    - `url` (str): The Supabase URL.
    - `index_name` (str): The name of the table where vectors will be stored and retrieved.

    ## Methods
    - `add(vectors: List[Vector], **kwargs: Any)`: Add vectors to the index.
    - `delete(ids: List[str] | None = None, **kwargs: Any)`: Delete vectors from the index.
    - `search(vector: Vector | None = None, limit: int = 1, **kwargs: Any) -> List[Vector]`: Search for vectors in the index.
    """

    @override
    def __init__(self, api_key: str, url: str, index_name: str):
        """Initialize a SupabaseVectorStore object for managing vectors in a Supabase table.

        Args:
            api_key (str): The API key for authentication with the Supabase service.
            url (str): The Supabase URL.
            index_name (str): The name of the table where vectors will be stored and retrieved.
        """
        self.__client = create_client(url, api_key)
        self.__index_name = index_name

    @override
    def add(self, vectors: List[Vector], **kwargs: Any):
        """Add vectors to the index.

        Args:
            vectors (List[Vector]): A list of Vector objects to add to the index. Note that each vector must have a unique ID.

        Raises:
            ValueError: If any of the vectors do not have embeddings.

        Note:
            - Requires a table with columns: `id` (text), `vector` (vector(1536 or dimension of embeddings model used)), `metadata` (json), `created_at` (timestamp).
            - **Vector type is enabled with the vector extension for postgres in supabase**.
            - Requires default value of `id` to `gen_random_uuid()`.
        """
        for vector in vectors:
            # if not vector.id:
            #     raise ValueError("Vector ID cannot be empty when adding to Supabase.")
            if not vector.embeddings:
                raise ValueError(
                    "Vector embeddings cannot be empty when adding to Supabase."
                )
            vec = {"vector": vector.embeddings, "metadata": vector.metadata}
            if vector.id is not None and vector.id != "":
                print("id is not none")
                vec["id"] = vector.id
            print(vec)
            self.__client.table(self.__index_name).insert(vec).execute()

    @override
    def delete(self, ids: List[str] | None = None, **kwargs: Any):
        """Delete vectors from the index.

        Args:
            ids (List[str] | None, optional): A list of vector IDs to delete. Defaults to None.
        """
        self.__client.table(self.__index_name).delete().in_("id", ids).execute()

    @override
    def search(
        self, vector: Vector | None = None, top_k: int = 1, **kwargs: Any
    ) -> List[Vector]:
        """
        Search for vectors in the index.

        Args:
            vector (Vector | None, optional): The query vector. Defaults to None.
            top_k (int, optional): the number of vectors to retrieve

        Returns:
            List[Vector]: A list of Vector objects containing the search results.

        -- Requires the following procedure (where you only change the value of the TABLENAME variable):

        ```sql
        drop function if exists similarity_search_TABLENAME (embedding vector (1536), match_count bigint);

        create or replace function similarity_search_TABLENAME(embedding vector(1536), match_count bigint)
        returns table (id text,similarity float, value vector(1536), ,metadata json)
        language plpgsql
        as $$
        begin
            return query
            select
                TABLENAME.id,
                (TABLENAME.vector <#> embedding) * -1 as similarity,
                TABLENAME.vector,
                TABLENAME.metadata
            from TABLENAME
            order by TABLENAME.vector <#> embedding
            limit match_count;
        end;
        $$;
        ```
        """
        query_response = self.__client.rpc(
            "similarity_search_" + self.__index_name,
            {"embedding": vector.embeddings, "match_count": top_k},
        ).execute()
        vectors = []
        print(query_response.data)
        for match in query_response.data:
            print(match)
            metadata = vector.metadata if vector else {}
            metadata.update(match["metadata"])
            metadata["score"] = match["similarity"]
            parsed_vector = [float(i) for i in match["value"][1:-1].split(",")]
            vectors.append(
                Vector(
                    embeddings=parsed_vector,
                    id=match["id"],
                    metadata=metadata,
                )
            )
        return vectors
